"""Axis-invariant slab extrusion for concave outlines, holes and islands.

At a fixed invariant coordinate, material consists of noncrossing intervals.
Every interval extrudes to a convex cell. Equal lateral ranks from disjoint
slabs may share a cap mesh: those slabs never overlap in the projected view.
"""
from __future__ import annotations
from bisect import bisect_right
from functools import lru_cache
import math


def _get(options,name,default=None):
    return options.get(name,default) if isinstance(options,dict) else getattr(options,name,default)


def _xy(t,s,axis):
    return (t,s) if axis == 'y' else (s,t)


def _ts(point,axis):
    return (point[0],point[1]) if axis == 'y' else (point[1],point[0])


def _area(points):
    return sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1]))/2


def _clean(points):
    result=[]
    for point in points:
        if not result or math.dist(point,result[-1]) > 1e-8:
            result.append(point)
    if len(result)>1 and math.dist(result[0],result[-1])<1e-8:
        result.pop()
    if len(result)<3 or abs(_area(result))<1e-10:
        return []
    return result if _area(result)>0 else list(reversed(result))


def _uv(x,y,width,height,axis,sign):
    if sign<0:
        if axis=='y':x=-x
        else:y=-y
    return x/width+.5,.5-y/height


def connected_meshes(spec):
    """Weld adjacent pieces and split disconnected components.

    Each output is one connected simple mesh with its true boundary first.
    This obeys Spine 4.2 Binary's T=2N-H-2 mesh topology requirement; disconnected
    islands are never hidden inside a fake hull or padded with fake triangles.
    """
    old_model=spec['model'];uv=spec['uvs'];keys={};model=[];uvs=[];old_to_new=[];first_original=[]
    for index,point in enumerate(old_model):
        key=tuple(round(value,8) for value in point)
        if key not in keys:
            keys[key]=len(model);model.append(point);uvs.append(tuple(uv[index*2:index*2+2]));first_original.append(index)
        old_to_new.append(keys[key])
    triangles=[]
    for i in range(0,len(spec['triangles']),3):
        ids=tuple(old_to_new[j] for j in spec['triangles'][i:i+3])
        if len(set(ids))<3:continue
        a,b,c=[model[j] for j in ids]
        if abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))<1e-11:continue
        triangles.append(ids)
    owners={}
    for index,triangle in enumerate(triangles):
        for a,b in zip(triangle,triangle[1:]+triangle[:1]):owners.setdefault(tuple(sorted((a,b))),[]).append(index)
    if any(len(value)>2 for value in owners.values()):
        raise ValueError('不規則分區產生重疊網格，請調整外框誤差。')
    neighbours=[set() for _ in triangles]
    for value in owners.values():
        if len(value)==2:
            a,b=value;neighbours[a].add(b);neighbours[b].add(a)
    unseen=set(range(len(triangles)));components=[]
    while unseen:
        seed=min(unseen);unseen.remove(seed);todo=[seed];component=[]
        while todo:
            current=todo.pop();component.append(current)
            for other in sorted(neighbours[current]):
                if other in unseen:unseen.remove(other);todo.append(other)
        components.append(sorted(component))
    result=[]
    for number,component in enumerate(components):
        selected=set(component);boundary=[]
        for index in component:
            triangle=triangles[index]
            for a,b in zip(triangle,triangle[1:]+triangle[:1]):
                if sum(owner in selected for owner in owners[tuple(sorted((a,b)))])==1:boundary.append((a,b))
        forward={a:b for a,b in boundary}
        if len(forward)!=len(boundary):raise ValueError('不規則分區邊界相接不明，請調整外框誤差。')
        hull=[];start=min(forward);current=start
        while current not in hull:
            hull.append(current);current=forward[current]
        if current!=start or len(hull)!=len(boundary):
            raise ValueError('不規則分區含有未分離的孔洞，請調整外框誤差。')
        used={vertex for index in component for vertex in triangles[index]}
        order=hull+sorted(used-set(hull));mapping={old:new for new,old in enumerate(order)}
        tri=tuple(mapping[vertex] for index in component for vertex in triangles[index])
        if len(tri)//3 != 2*len(order)-len(hull)-2:
            raise ValueError('不規則網格拓撲不完整，無法安全匯入 Spine。')
        parts=[]
        for part in spec.get('parts',()):
            vertices=tuple(old_to_new[i] for i in part)
            if all(vertex in used for vertex in vertices):parts.append(tuple(mapping[vertex] for vertex in vertices))
        item={**spec,'name':spec['name']+(f'_part_{number:02d}' if len(components)>1 else ''),
              'model':tuple(model[i] for i in order),'uvs':tuple(value for i in order for value in uvs[i]),
              'triangles':tri,'hull':len(hull),'parts':tuple(parts)}
        if 'vertex_weights' in spec:
            item['vertex_weights']=tuple(spec['vertex_weights'][first_original[i]] for i in order)
        result.append(item)
    return result


@lru_cache(maxsize=32)
def _geometry(loops,width,height,axis):
    if not loops:
        raise ValueError('不規則輪廓尚未解析，請先準備圖片並解析外框。')
    polygons=[[(x*width,y*height) for x,y in loop] for loop in loops]
    lateral=width if axis=='y' else height
    invariant=height if axis=='y' else width
    edges=[]
    levels={-invariant/2,invariant/2}
    for loop_index,polygon in enumerate(polygons):
        lengths=[math.dist(a,b) for a,b in zip(polygon,polygon[1:]+polygon[:1])]
        total=sum(lengths);distance=0.
        for index,(a,b) in enumerate(zip(polygon,polygon[1:]+polygon[:1])):
            if lengths[index]<1e-9:raise ValueError('不規則輪廓含有重複頂點。')
            t0,s0=_ts(a,axis);t1,s1=_ts(b,axis)
            levels.update((s0,s1))
            edges.append({'a':a,'b':b,'ts':(t0,s0,t1,s1),'loop':loop_index,
                          'u0':distance/total,'u1':(distance+lengths[index])/total})
            distance+=lengths[index]
    levels=sorted(levels)
    crossings_at={}
    for level in levels:
        values={-lateral/2,lateral/2}
        for edge in edges:
            a,u,b,v=edge['ts']
            if abs(v-u)<1e-10:
                if abs(level-u)<1e-8:values.update((a,b))
            elif min(u,v)-1e-8<=level<=max(u,v)+1e-8:
                values.add(a+(b-a)*(level-u)/(v-u))
        crossings_at[level]=sorted(values)
    groups={};bands=[];max_rank=0;piece_count=0
    for slab,(s0,s1) in enumerate(zip(levels,levels[1:])):
        mid=(s0+s1)/2
        crossings=[]
        for edge in edges:
            a,u,b,v=edge['ts']
            if min(u,v)<mid<max(u,v):
                at=lambda s:a+(b-a)*(s-u)/(v-u)
                crossings.append((at(mid),at(s0),at(s1)))
        crossings.sort()
        if len(crossings)%2:
            raise ValueError('不規則輪廓相交或未封閉，無法建立厚度。')
        boundaries=[(-lateral/2,-lateral/2,-lateral/2),*crossings,(lateral/2,lateral/2,lateral/2)]
        cells=[]
        for rank,(left,right) in enumerate(zip(boundaries,boundaries[1:])):
            lo0,lo1,hi0,hi1=left[1],left[2],right[1],right[2]
            if (lo0+lo1)/2>=(hi0+hi1)/2-1e-9:continue
            bottom=[v for v in crossings_at[s0] if lo0+1e-8<v<hi0-1e-8]
            top=[v for v in crossings_at[s1] if lo1+1e-8<v<hi1-1e-8]
            polygon=_clean([_xy(t,s0,axis) for t in (lo0,*bottom,hi0)]+
                           [_xy(t,s1,axis) for t in (hi1,*reversed(top),lo1)])
            if not polygon:continue
            groups.setdefault(rank,[]).append(tuple(polygon));piece_count+=1
            cells.append((rank,left[0],right[0]))
            max_rank=max(max_rank,rank)
        bands.append(cells)
    if piece_count>8192:
        raise ValueError('外框過於複雜，請提高簡化誤差或調整透明度門檻。')
    specs=[]
    for rank,parts in sorted(groups.items()):
        solid=bool(rank%2)
        for path,sign in (('back',-1),('front',1)):
            model=[];uvs=[];triangles=[];part_ids=[]
            for polygon in parts:
                first=len(model);count=len(polygon)
                model.extend((x,y,sign) for x,y in polygon)
                uvs.extend(value for x,y in polygon for value in _uv(x,y,width,height,axis,sign))
                center=tuple(sum(point[i] for point in polygon)/count for i in (0,1))
                model.append((*center,sign));uvs.extend(_uv(*center,width,height,axis,sign))
                for i in range(count):
                    indices=(first+i,first+(i+1)%count,first+count)
                    triangles.extend(indices if sign>0 else tuple(reversed(indices)))
                part_ids.append(tuple(range(first,first+count)))
            specs.extend(connected_meshes({'name':f'irregular_{"cap" if solid else "air"}_{rank:03d}_{path}',
                'kind':path if solid else 'irregular_air','path':path,'cell_rank':rank,
                'solid':solid,'model':tuple(model),'uvs':tuple(uvs),'triangles':tuple(triangles),
                'hull':0,'parts':tuple(part_ids),'normal':(0.,0.,float(sign)),'local_order':200000 if sign<0 else 300000}))
    for edge_index,edge in enumerate(edges):
        a,b=edge['a'],edge['b'];t0,s0,t1,s1=edge['ts'];dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        parameters={0.,1.}
        if abs(s1-s0)>1e-10:
            parameters.update((s-s0)/(s1-s0) for s in levels if min(s0,s1)<s<max(s0,s1))
        parameters=sorted(parameters)
        for part,(begin,end) in enumerate(zip(parameters,parameters[1:])):
            first=tuple(a[i]+(b[i]-a[i])*begin for i in (0,1));second=tuple(a[i]+(b[i]-a[i])*end for i in (0,1))
            middle=tuple((first[i]+second[i])/2 for i in (0,1));t,s=_ts(middle,axis)
            band=max(0,min(len(bands)-1,bisect_right(levels,s)-1))
            rank=next((rank for rank,left,right in bands[band] if rank%2 and left-1e-7<=t<=right+1e-7),1)
            u0=edge['u0']+(edge['u1']-edge['u0'])*begin;u1=edge['u0']+(edge['u1']-edge['u0'])*end
            specs.append({'name':f'irregular_wall_{edge_index:03d}_{part:03d}','kind':'edge','path':'edge',
                'cell_rank':rank,'solid':True,'model':((*first,1.),(*first,-1.),(*second,-1.),(*second,1.)),
                'uvs':(u0,0.,u0,1.,u1,1.,u1,0.),'triangles':(0,1,2,2,3,0),'hull':4,
                'normal':(dy/length,-dx/length,0.),'local_order':edge_index*1024+part})
    if len(specs)>4096 or sum(len(spec['model']) for spec in specs)>60000:
        raise ValueError('外框網格過於複雜，請提高簡化誤差或調整透明度門檻。')
    return tuple(specs),max_rank,piece_count,len(levels)-1


def irregular_geometry(options,width,height):
    return _geometry(tuple(_get(options,'irregular_contours',())),float(width),float(height),_get(options,'axis','y'))[0]


def irregular_statistics(options,width,height):
    specs,rank,pieces,slabs=_geometry(tuple(_get(options,'irregular_contours',())),float(width),float(height),_get(options,'axis','y'))
    return {'slabs':slabs,'interval_pieces':pieces,'lateral_ranks':rank+1,'surfaces':len(specs),
            'vertices':sum(len(spec['model']) for spec in specs),'cap_meshes':sum(spec['kind']!='edge' for spec in specs),
            'wall_meshes':sum(spec['kind']=='edge' for spec in specs)}


def irregular_pose(angle_degrees,options,width,height,depth_scale=1):
    angle=math.radians(angle_degrees%360);lookahead=angle+1e-9
    sine,cosine=math.sin(angle),math.cos(angle)
    visible_sine,visible_cosine=math.sin(lookahead),math.cos(lookahead)
    axis=_get(options,'axis','y');half=_get(options,'thickness',24)*depth_scale/2
    specs,max_rank,_,_=_geometry(tuple(_get(options,'irregular_contours',())),float(width),float(height),axis)
    descending=(visible_sine>0) if axis=='y' else (visible_sine<0)
    result=[]
    for spec in specs:
        nx,ny,nz=spec['normal'];model=[(x,y,z*half) for x,y,z in spec['model']]
        vertices=[]
        for x,y,z in model:
            vertices.extend((x*cosine+z*sine,y) if axis=='y' else (x,y*cosine-z*sine))
        if spec['kind']=='edge':
            facing=(-nx if axis=='y' else ny)*visible_sine
            visible=facing>0 and half>0
            factor=.62+.38*max(0.,facing) if _get(options,'shade_edge',True) else 1.
        else:
            visible=nz*visible_cosine>0
            if _get(options,'shade_faces',False):
                light=max(0.,nz*math.cos(angle-math.radians(_get(options,'light_angle',0))))
                factor=_get(options,'min_brightness',.4)+(1-_get(options,'min_brightness',.4))*light**_get(options,'shade_curve',1)
            else:factor=1.
        channel=round(max(0.,min(1.,factor))*255)
        rank=max_rank-spec['cell_rank'] if descending else spec['cell_rank']
        result.append({'name':spec['name'],'kind':spec['kind'],'path':spec['path'],'vertices':vertices,
            'uvs':list(spec['uvs']),'triangles':list(spec['triangles']),'hull':spec['hull'],
            'visible':visible,'color':f'{channel:02x}'*3+'ff','normal':spec['normal'],
            'model_vertices':[value for point in model for value in point],'solid':spec['solid'],
            'parts':spec.get('parts',()),'cell_rank':spec['cell_rank'],'irregular':True,
            'draw_order':rank*1000000+spec['local_order']})
        result[-1]['view_depths']=[(-x*sine+z*cosine if axis=='y' else y*sine+z*cosine) for x,y,z in model]
    return result


def _mix_weights(a,b,fraction):
    values={i:value*(1-fraction) for i,value in a}
    for i,value in b:values[i]=values.get(i,0.)+value*fraction
    return tuple(sorted((i,value) for i,value in values.items() if abs(value)>1e-14))


def _clip_weighted(polygon,limit,greater,width,height,direction):
    from spine_turn_coin_fx import _dot
    if not polygon:return []
    result=[];before=polygon[-1]
    previous=(_dot(before[0],before[1],width,height,direction)-limit)*(1 if greater else -1)
    for after in polygon:
        current=(_dot(after[0],after[1],width,height,direction)-limit)*(1 if greater else -1)
        if (previous>=0)!=(current>=0):
            fraction=previous/(previous-current)
            result.append((before[0]+(after[0]-before[0])*fraction,
                           before[1]+(after[1]-before[1])*fraction,_mix_weights(before[2],after[2],fraction)))
        if current>=0:result.append(after)
        before,previous=after,current
    clean=[]
    for point in result:
        if not clean or math.dist(point[:2],clean[-1][:2])>1e-11:clean.append(point)
    if len(clean)>1 and math.dist(clean[0][:2],clean[-1][:2])<1e-11:clean.pop()
    return clean


@lru_cache(maxsize=64)
def _effect_templates(uvs,parts,width,height,angle):
    from spine_turn_coin_fx import _direction
    direction=_direction(angle);span=abs(direction[0])*width+abs(direction[1])*height
    result=[]
    for stripe in range(32):
        lower,upper=-span/2+span*stripe/32,-span/2+span*(stripe+1)/32
        model=[];texture=[];weights=[];triangles=[];piece_ids=[]
        for part in parts:
            polygon=[(uvs[i*2],uvs[i*2+1],((i,1.),)) for i in part]
            polygon=_clip_weighted(_clip_weighted(polygon,lower,True,width,height,direction),upper,False,width,height,direction)
            if len(polygon)<3 or abs(_area([point[:2] for point in polygon]))<1e-12:continue
            start=len(model);count=len(polygon)
            center=(sum(p[0] for p in polygon)/count,sum(p[1] for p in polygon)/count)
            combined={}
            for point in polygon:
                for i,value in point[2]:combined[i]=combined.get(i,0.)+value/count
            nodes=polygon+[(*center,tuple(sorted(combined.items())))]
            model.extend((u,v,0.) for u,v,w in nodes);texture.extend(value for u,v,w in nodes for value in (u,v))
            weights.extend(w for u,v,w in nodes)
            triangles.extend(value for i in range(count) for value in (start+i,start+(i+1)%count,start+count))
            piece_ids.append(tuple(range(start,start+count)))
        if not model:continue
        spec={'name':f'coin_shine_{stripe:02d}','model':tuple(model),'uvs':tuple(texture),
              'triangles':tuple(triangles),'parts':tuple(piece_ids),'vertex_weights':tuple(weights)}
        for component in connected_meshes(spec):
            result.append((component,stripe,(lower+upper)/2))
    return tuple(result)


def irregular_effect_surfaces(base_surfaces,options,progress,width,height,keep=None):
    """`keep(coordinate)` (rasterizers only) skips hidden or rejected light cells
    before their vertices are blended; the over-limit check still counts them."""
    from spine_turn_coin_fx import sweep_alpha
    result=[];total=0
    for parent in base_surfaces:
        if parent.get('kind') not in ('front','back') or not parent.get('solid',False):continue
        templates=_effect_templates(tuple(parent['uvs']),tuple(parent['parts']),width,height,_get(options,'coin_shine_angle',-25))
        positions=list(zip(parent['vertices'][::2],parent['vertices'][1::2]))
        models=list(zip(*[iter(parent['model_vertices'])]*3))
        total+=len(templates)
        if keep is not None and not parent['visible']:continue
        for template,stripe,coordinate in templates:
            if keep is not None and not keep(coordinate):continue
            weights=template['vertex_weights']
            vertices=[sum(positions[i][axis]*value for i,value in node) for node in weights for axis in (0,1)]
            alpha=sweep_alpha(progress,coordinate,options,width,height)
            if keep is not None:
                # A rasterizer reads screen positions only; skip model/depth blending.
                result.append({'name':parent['name']+'_'+template['name'],'kind':'coin_fx',
                    'path':'coin-shine-'+parent['path'],'vertices':vertices,'uvs':list(template['uvs']),
                    'triangles':list(template['triangles']),'hull':template['hull'],'visible':True,
                    'color':f'ffffff{round(alpha*255):02x}','source_face':parent['name'],
                    'source_coordinate':coordinate,'effect':'light_sweep','irregular':True,'solid':False,
                    'draw_order':parent['draw_order']+(stripe+1)*.001})
                continue
            model=[sum(models[i][axis]*value for i,value in node) for node in weights for axis in (0,1,2)]
            depths=[sum(parent['view_depths'][i]*value for i,value in node) for node in weights]
            result.append({'name':parent['name']+'_'+template['name'],'kind':'coin_fx',
                'path':'coin-shine-'+parent['path'],'vertices':vertices,'uvs':list(template['uvs']),
                'triangles':list(template['triangles']),'hull':template['hull'],'visible':parent['visible'],
                'color':f'ffffff{round(alpha*255):02x}','source_face':parent['name'],'cell_weights':weights,
                'source_coordinate':coordinate,'effect':'light_sweep','model_vertices':model,'view_depths':depths,
                'irregular':True,'solid':False,'draw_order':parent['draw_order']+(stripe+1)*.001})
    if total>2048:
        raise ValueError('不規則掃光分區過多，請提高外框簡化誤差，或關閉掃光。')
    return result
