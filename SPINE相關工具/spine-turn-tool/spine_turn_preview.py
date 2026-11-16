"""Small straight-alpha mesh renderer shared by the desktop preview and QA."""
from __future__ import annotations

import math
import numpy as np
from PIL import Image, ImageDraw, ImageChops
from spine_turn_core import animation_pose_at, motion_at, ordered_surfaces, transform_vertices_for_motion


def _surface_tint(surface):
    if 'tint' in surface:
        tint = tuple(float(value) for value in surface['tint'])
    else:
        color = surface.get('color', 'ffffffff')
        tint = tuple(int(color[index:index + 2], 16) / 255 for index in (0, 2, 4, 6))
    if len(tint) != 4 or not all(math.isfinite(value) for value in tint):
        raise ValueError('Mesh tint needs four finite RGBA values.')
    return tuple(min(1., max(0., value)) for value in tint)


def _triangles(surface, vertex_count):
    triangles = surface.get('triangles')
    if triangles is None:
        if vertex_count != 4:
            raise ValueError('A non-quad mesh needs explicit triangle indices.')
        triangles = [0, 1, 2, 2, 3, 0]
    if len(triangles) % 3 or any(isinstance(index, bool) or not isinstance(index, int)
            or not 0 <= index < vertex_count for index in triangles):
        raise ValueError('Mesh triangle indices are invalid.')
    return triangles


def _affine_quad(points, uv, triangles):
    if len(points) != 4 or len(uv) != 8 or len(triangles) != 6:
        return False
    topology = {frozenset(triangles[index:index + 3]) for index in (0, 3)}
    valid = ({frozenset((0, 1, 2)), frozenset((0, 2, 3))},
             {frozenset((0, 1, 3)), frozenset((1, 2, 3))})
    return topology in valid and all(abs(points[0][axis] + points[2][axis] -
        points[1][axis] - points[3][axis]) <= 1e-5 for axis in (0, 1)) and all(
        abs(uv[axis] + uv[axis + 4] - uv[axis + 2] - uv[axis + 6]) <= 1e-8 for axis in (0, 1))


_PERSISTENT_TEXTURE_PIXELS = 4_000_000   # 64 MB of float32 RGBA per texture at most
_SAMPLE_BLOCK = 4096                     # pixels per pass; keeps temporaries in CPU cache
_background_cache = {}


def _texture_pma(texture, cache):
    """Premultiplied float texture. Entries keep the image alive, so an id
    can never be reused by different artwork while its entry exists."""
    entry = cache.get(id(texture))
    if entry is None or entry[0] is not texture:
        data = np.asarray(texture.convert('RGBA'), dtype=np.float32) / 255.
        data[:, :, :3] *= data[:, :, 3:4]
        entry = cache[id(texture)] = (texture, data)
    return entry[1]


def _texture_cache(prepared):
    """Converted textures live as long as their prepared artwork, instead of
    being converted again for every frame. Very large art stays per-frame."""
    try:
        if all(image.width * image.height <= _PERSISTENT_TEXTURE_PIXELS
               for image in prepared.values() if isinstance(image, Image.Image)):
            return prepared.setdefault('_preview_pma_textures', {})
    except (AttributeError, TypeError):
        pass
    return {}


def _canvas(size, background):
    """Background (including the checker pattern) is drawn once per view."""
    key = (tuple(size), background)
    cached = _background_cache.get(key)
    if cached is None:
        width, height = size
        colors = {"dark": (22, 27, 37, 255), "light": (235, 239, 245, 255),
                  "transparent": (0, 0, 0, 0)}
        cached = Image.new("RGBA", size, colors.get(background, (31, 37, 49, 255)))
        if background == "checker":
            draw = ImageDraw.Draw(cached)
            for y in range(0, height, 20):
                for x in range(0, width, 20):
                    if (x // 20 + y // 20) % 2:
                        draw.rectangle((x, y, x + 19, y + 19), fill=(37, 44, 57, 255))
        if len(_background_cache) >= 8:
            _background_cache.clear()
        _background_cache[key] = cached
    return cached.copy()


def _bilinear_pma(texture, u, v):
    height, width = texture.shape[:2]
    x = np.clip(u * width - .5, 0, width - 1)
    y = np.clip(v * height - .5, 0, height - 1)
    x0, y0 = np.floor(x).astype(np.intp), np.floor(y).astype(np.intp)
    x1, y1 = np.minimum(x0 + 1, width - 1), np.minimum(y0 + 1, height - 1)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    above = texture[y0, x0] * (1 - fx) + texture[y0, x1] * fx
    below = texture[y1, x0] * (1 - fx) + texture[y1, x1] * fx
    return above * (1 - fy) + below * fy


def _triangle_patch(texture, points, uv, triangles, size, tint, cache):
    """Rasterize a whole mesh once, with top-left shared-edge ownership.

    Pixel-center barycentrics interpolate UVs. Sampling uses premultiplied
    colors so hidden RGB in transparent texels cannot produce dark/color halos.
    The returned patch has straight alpha for Pillow's alpha_composite.
    """
    width, height = size
    left = max(0, math.floor(min(point[0] for point in points)))
    top = max(0, math.floor(min(point[1] for point in points)))
    right = min(width, math.ceil(max(point[0] for point in points)))
    bottom = min(height, math.ceil(max(point[1] for point in points)))
    if right <= left or bottom <= top or not triangles:
        return None
    pixels = np.zeros((bottom - top, right - left, 4), dtype=np.uint8)
    claimed = np.zeros((bottom - top, right - left), dtype=bool)
    source = _texture_pma(texture, cache)
    coordinates = np.asarray(points, dtype=np.float64)
    texcoords = np.asarray(uv, dtype=np.float64).reshape(-1, 2)

    def edge(a, b, x, y):
        return (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])

    def top_left(a, b):
        dy, dx = b[1] - a[1], b[0] - a[0]
        return dy < 0 or (abs(dy) < 1e-12 and dx > 0)

    for index in range(0, len(triangles), 3):
        indices = list(triangles[index:index + 3])
        a, b, c = coordinates[indices]
        area = edge(a, b, c[0], c[1])
        if abs(area) < 1e-8:
            continue
        if area < 0:
            indices[1], indices[2] = indices[2], indices[1]
            a, b, c = coordinates[indices]
            area = -area
        x0 = max(left, math.floor(min(a[0], b[0], c[0])))
        y0 = max(top, math.floor(min(a[1], b[1], c[1])))
        x2 = min(right, math.ceil(max(a[0], b[0], c[0])))
        y2 = min(bottom, math.ceil(max(a[1], b[1], c[1])))
        if x2 <= x0 or y2 <= y0:
            continue
        yy, xx = np.mgrid[y0:y2, x0:x2]
        xx, yy = xx + .5, yy + .5
        weights = (edge(b, c, xx, yy) / area, edge(c, a, xx, yy) / area,
                   edge(a, b, xx, yy) / area)
        inside = np.ones(xx.shape, dtype=bool)
        for value, first, second in zip(weights, (b, c, a), (c, a, b)):
            inside &= (value > 1e-10) | ((np.abs(value) <= 1e-10) & top_left(first, second))
        occupied = claimed[y0 - top:y2 - top, x0 - left:x2 - left]
        inside &= ~occupied
        if not np.any(inside):
            continue
        barycentric = np.stack([value[inside] for value in weights], axis=1)
        texture_points = barycentric @ texcoords[indices]
        samples = _bilinear_pma(source, texture_points[:, 0], texture_points[:, 1])
        samples[:, :3] *= np.asarray(tint[:3]) * tint[3]
        samples[:, 3] *= tint[3]
        straight = np.zeros_like(samples)
        straight[:, 3] = samples[:, 3]
        np.divide(samples[:, :3], samples[:, 3:4], out=straight[:, :3], where=samples[:, 3:4] > 1e-12)
        encoded = np.clip(np.floor(straight * 255 + .5), 0, 255).astype(np.uint8)
        patch = pixels[y0 - top:y2 - top, x0 - left:x2 - left]
        patch[inside] = encoded
        occupied[inside] = True
    return Image.fromarray(pixels), (left, top)


def _planar_template(surface, cache):
    """Static topology/UV data for one connected irregular mesh component."""
    uv = tuple(surface['uvs'])
    triangles = tuple(surface['triangles'])
    hull = int(surface.get('hull', 0))
    key = (uv, triangles, hull)
    entry = cache.get(surface['name'])
    if entry is not None and entry[0] == key:
        return entry[1]
    count = len(uv)//2
    template = None
    if hull >= 3 and hull <= count:
        validated = _triangles(surface, count)
        owners = {}
        for offset in range(0, len(validated), 3):
            triangle = tuple(validated[offset:offset+3])
            for a,b in zip(triangle, triangle[1:]+triangle[:1]):
                owners.setdefault(tuple(sorted((a,b))), []).append(offset//3)
        expected = {tuple(sorted((i,(i+1)%hull))) for i in range(hull)}
        actual = {edge for edge,value in owners.items() if len(value)==1}
        if expected == actual and all(len(value)<=2 for value in owners.values()):
            tex = np.asarray(uv, dtype=np.float64).reshape(-1,2)
            first = int(np.argmin(tex[:,0]))
            delta = tex-tex[first]
            second = int(np.argmax(np.sum(delta*delta, axis=1)))
            direction = tex[second]-tex[first]
            third = int(np.argmax(np.abs(direction[0]*delta[:,1]-direction[1]*delta[:,0])))
            basis = np.column_stack((tex[second]-tex[first],tex[third]-tex[first]))
            if abs(np.linalg.det(basis)) > 1e-14:
                tri = np.asarray(validated,dtype=np.intp).reshape(-1,3)
                boundary_owner = np.array([owners[tuple(sorted((i,(i+1)%hull)))][0] for i in range(hull)],dtype=np.intp)
                template = {'uv':tex,'triangles':tri,'hull':hull,'indices':(first,second,third),
                            'inverse_uv':np.linalg.inv(basis),'boundary_owner':boundary_owner}
    cache[surface['name']] = (key,template)
    return template


def _reference_row_coverage(coordinates, triangles, rows, left, right):
    """Resolve pixel-center vertex ties with the reference halfspace rules."""
    claimed=np.zeros((len(rows),right-left),dtype=bool)
    if not len(rows):return claimed
    corners=coordinates[triangles]
    ymin=np.floor(np.min(corners[:,:,1],axis=1))
    ymax=np.ceil(np.max(corners[:,:,1],axis=1))
    candidates=np.flatnonzero(np.any((rows[:,None]>=ymin)&(rows[:,None]<ymax),axis=0))
    for index in candidates:
        a,b,c=corners[index]
        area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        if abs(area)<1e-8:continue
        if area<0:b,c=c,b;area=-area
        x0=max(left,math.floor(min(a[0],b[0],c[0])));x1=min(right,math.ceil(max(a[0],b[0],c[0])))
        if x1<=x0:continue
        xx=np.arange(x0,x1,dtype=np.float64)[None,:]+.5;yy=rows[:,None]+.5
        inside=np.ones((len(rows),x1-x0),dtype=bool)
        for first,second in ((b,c),(c,a),(a,b)):
            value=((second[0]-first[0])*(yy-first[1])-(second[1]-first[1])*(xx-first[0]))/area
            dy,dx=second[1]-first[1],second[0]-first[0]
            owns=dy<0 or (abs(dy)<1e-12 and dx>0)
            inside &= (value>1e-10)|((np.abs(value)<=1e-10)&owns)
        inside &= (rows[:,None]>=math.floor(min(a[1],b[1],c[1])))&(rows[:,None]<math.ceil(max(a[1],b[1],c[1])))
        claimed[:,x0-left:x1-left] |= inside
    return claimed


def _planar_job(texture, points, template, size, tint):
    """Rasterize the true polygon boundary, then sample one global affine map.

    Non-affine or unsupported topology returns False for the reference path.
    No bounding hull is substituted for the actual concave boundary.
    """
    if template is None:
        return False
    coordinates = np.asarray(points,dtype=np.float64)
    i,j,k = template['indices']
    affine = np.column_stack((coordinates[j]-coordinates[i],coordinates[k]-coordinates[i])) @ template['inverse_uv']
    det = float(np.linalg.det(affine))
    if abs(det)<1e-10:
        return False
    translation = coordinates[i]-affine@template['uv'][i]
    if np.max(np.abs(template['uv']@affine.T+translation-coordinates))>2e-6:
        return False
    tri = coordinates[template['triangles']]
    areas = ((tri[:,1,0]-tri[:,0,0])*(tri[:,2,1]-tri[:,0,1])-
             (tri[:,1,1]-tri[:,0,1])*(tri[:,2,0]-tri[:,0,0]))
    if np.any(np.abs(areas)<1e-8):
        return False
    width,height = size
    lowest=coordinates.min(axis=0);highest=coordinates.max(axis=0)
    left=max(0,math.floor(float(lowest[0])))
    right=min(width,math.ceil(float(highest[0])))
    top=max(0,math.floor(float(lowest[1])))
    bottom=min(height,math.ceil(float(highest[1])))
    if right<=left or bottom<=top:
        return None
    boundary = coordinates[:template['hull']]
    following = np.concatenate((boundary[1:],boundary[:1]))
    delta = following-boundary
    nonhorizontal = np.abs(delta[:,1])>1e-12
    starts,ends = boundary[nonhorizontal],following[nonhorizontal]
    dy = ends[:,1]-starts[:,1]
    yc = np.arange(top,bottom,dtype=np.float64)+.5
    # Pixel-center even/odd scan conversion: upper and left edges own ties.
    epsilon = 1e-9
    active = ((yc[:,None]>=np.minimum(starts[:,1],ends[:,1])-epsilon)&
              (yc[:,None]<np.maximum(starts[:,1],ends[:,1])-epsilon))
    nearest=np.rint(boundary[:,1]-.5)
    centered=np.abs(boundary[:,1]-.5-nearest)<1e-7
    if centered.any():
        critical=np.unique(nearest.astype(np.intp)[centered])
        critical=critical[(critical>=top)&(critical<bottom)]
    else:
        critical=nearest[:0].astype(np.intp)
    if len(critical):active[critical-top,:]=False
    rows,edges = np.nonzero(active)
    if not len(rows) and not len(critical):return None
    intersections = starts[edges,0]+(yc[rows]-starts[edges,1])*(ends[edges,0]-starts[edges,0])/dy[edges]
    # Match the reference triangle's dimensionless boundary tolerance.
    edge_areas = np.abs(areas[template['boundary_owner'][nonhorizontal]])
    intersections -= 1e-10*edge_areas[edges]/np.abs(dy[edges])
    ordering = np.lexsort((intersections,rows))
    rows,intersections = rows[ordering],intersections[ordering]
    if len(rows)%2 or not np.array_equal(rows[::2],rows[1::2]):
        return False
    x0=np.maximum(left,np.ceil(intersections[::2]-.5).astype(np.intp))
    x1=np.minimum(right,np.ceil(intersections[1::2]-.5).astype(np.intp))
    lengths=np.maximum(0,x1-x0)
    good=lengths>0
    rows,x0,lengths=rows[::2][good],x0[good],lengths[good]
    total=int(np.sum(lengths))
    yy=np.repeat(rows+top,lengths)
    xx=np.repeat(x0,lengths)+np.arange(total)-np.repeat(np.cumsum(lengths)-lengths,lengths)
    if len(critical):
        cover=_reference_row_coverage(coordinates,template['triangles'],critical,left,right)
        row,column=np.nonzero(cover)
        yy=np.concatenate((yy,critical[row]));xx=np.concatenate((xx,column+left))
    if not len(xx):return None
    inverse=np.linalg.inv(affine)
    centers=np.empty((len(xx),2),dtype=np.float64)
    centers[:,0]=xx;centers[:,1]=yy;centers+=.5;centers-=translation
    uv=centers@inverse.T
    return {'texture':texture,'template':template,'points':coordinates,'xx':xx,'yy':yy,'uv':uv,
            'left':left,'top':top,'right':right,'bottom':bottom,'tint':tint}


def _wall_jobs(inputs,size):
    """Vectorized affine/scan conversion for the many small irregular walls."""
    if not inputs:return {}
    width,height=size
    coordinates=np.asarray([item['points'] for item in inputs],dtype=np.float64)
    uv=np.asarray([item['uv'] for item in inputs],dtype=np.float64).reshape(-1,4,2)
    origin=coordinates[:,0];a=coordinates[:,3]-origin;b=coordinates[:,1]-origin
    det=a[:,0]*b[:,1]-a[:,1]*b[:,0]
    valid=(np.abs(det)>1e-8)&(np.max(np.abs(coordinates[:,2]-(origin+a+b)),axis=1)<2e-6)
    valid &= (np.abs(uv[:,0,0]-uv[:,1,0])<1e-12)&(np.abs(uv[:,2,0]-uv[:,3,0])<1e-12)
    valid &= (np.abs(uv[:,0,1]-uv[:,3,1])<1e-12)&(np.abs(uv[:,1,1]-uv[:,2,1])<1e-12)
    valid &= np.all(np.abs(coordinates[:,:,1]-.5-np.rint(coordinates[:,:,1]-.5))>=1e-7,axis=1)
    results={index:False for index in range(len(inputs))}
    chosen=np.flatnonzero(valid)
    if not len(chosen):return results
    points=coordinates[chosen];a=a[chosen];b=b[chosen];det=det[chosen];origin=origin[chosen];tex=uv[chosen]
    following=np.roll(points,-1,axis=1);delta=following-points
    start=np.maximum(0,np.ceil(np.minimum(points[:,:,1],following[:,:,1])-.5-1e-9)).astype(np.intp)
    end=np.minimum(height,np.ceil(np.maximum(points[:,:,1],following[:,:,1])-.5-1e-9)).astype(np.intp)
    lengths=np.maximum(0,end-start)
    lengths[np.abs(delta[:,:,1])<=1e-12]=0
    flat_lengths=lengths.ravel();total=int(np.sum(flat_lengths))
    if not total:
        for index in chosen:results[int(index)]=None
        return results
    edge=np.repeat(np.arange(len(chosen)*4),flat_lengths)
    row=np.repeat(start.ravel(),flat_lengths)+np.arange(total)-np.repeat(np.cumsum(flat_lengths)-flat_lengths,flat_lengths)
    owner=edge//4;vertices=points.reshape(-1,2);directions=delta.reshape(-1,2)
    x=vertices[edge,0]+(row+.5-vertices[edge,1])*directions[edge,0]/directions[edge,1]
    x-=1e-10*np.abs(det[owner])/np.abs(directions[edge,1])
    order=np.lexsort((x,row,owner));owner,row,x=owner[order],row[order],x[order]
    if len(row)%2 or not np.array_equal(owner[::2],owner[1::2]) or not np.array_equal(row[::2],row[1::2]):return results
    first=np.maximum(0,np.ceil(x[::2]-.5).astype(np.intp));last=np.minimum(width,np.ceil(x[1::2]-.5).astype(np.intp))
    lengths=np.maximum(0,last-first);good=lengths>0
    owner,row,first,lengths=owner[::2][good],row[::2][good],first[good],lengths[good]
    total=int(np.sum(lengths))
    pixel_owner=np.repeat(owner,lengths);yy=np.repeat(row,lengths)
    xx=np.repeat(first,lengths)+np.arange(total)-np.repeat(np.cumsum(lengths)-lengths,lengths)
    u_span=tex[:,3,0]-tex[:,0,0];v_span=tex[:,1,1]-tex[:,0,1]
    ux=u_span*b[:,1]/det;uy=-u_span*b[:,0]/det
    vx=-v_span*a[:,1]/det;vy=v_span*a[:,0]/det
    u0=tex[:,0,0]-ux*origin[:,0]-uy*origin[:,1]
    v0=tex[:,0,1]-vx*origin[:,0]-vy*origin[:,1]
    texture_points=np.column_stack((ux[pixel_owner]*(xx+.5)+uy[pixel_owner]*(yy+.5)+u0[pixel_owner],
                                    vx[pixel_owner]*(xx+.5)+vy[pixel_owner]*(yy+.5)+v0[pixel_owner]))
    counts=np.bincount(pixel_owner,minlength=len(chosen));offset=0
    for local,index in enumerate(chosen):
        count=int(counts[local]);item=inputs[int(index)]
        if not count:results[int(index)]=None;continue
        points=coordinates[index]
        results[int(index)]={'texture':item['texture'],'points':points,'xx':xx[offset:offset+count],
            'yy':yy[offset:offset+count],'uv':texture_points[offset:offset+count],
            'left':max(0,math.floor(float(np.min(points[:,0])))),
            'top':max(0,math.floor(float(np.min(points[:,1])))),
            'right':min(width,math.ceil(float(np.max(points[:,0])))),
            'bottom':min(height,math.ceil(float(np.max(points[:,1])))),'tint':item['tint']}
        offset+=count
    return results


def _encode_pma(samples,tints):
    samples[:,:3] *= tints[:,:3]*tints[:,3:4]
    samples[:,3] *= tints[:,3]
    straight=np.zeros_like(samples)
    straight[:,3]=samples[:,3]
    np.divide(samples[:,:3],samples[:,3:4],out=straight[:,:3],where=samples[:,3:4]>1e-12)
    return np.clip(np.floor(straight*255+.5),0,255).astype(np.uint8)


def _sample_block(flat,width,height,u,v,factors,out):
    """`_bilinear_pma` + `_encode_pma` for one cache-sized block, in place.

    Every arithmetic step and its order match the two reference functions, so
    the bytes are identical; only the temporaries are smaller and reused.
    """
    x=u*width;x-=.5;np.clip(x,0,width-1,out=x)
    y=v*height;y-=.5;np.clip(y,0,height-1,out=y)
    x0=x.astype(np.intp);y0=y.astype(np.intp)      # x, y >= 0: truncation is floor
    x-=x0;y-=y0
    x1=np.minimum(x0+1,width-1);y1=np.minimum(y0+1,height-1)
    y0*=width;y1*=width
    fx=x[:,None];fy=y[:,None];gx=1-fx
    above=flat.take(y0+x0,axis=0)*gx;above+=flat.take(y0+x1,axis=0)*fx
    below=flat.take(y1+x0,axis=0)*gx;below+=flat.take(y1+x1,axis=0)*fx
    above*=1-fy;below*=fy;above+=below
    if factors is not None:above*=factors
    alpha=above[:,3:4]
    if not (alpha.min()==1. and alpha.max()==1.):
        color=above[:,:3];solid=alpha>1e-12
        np.divide(color,alpha,out=color,where=solid)
        color[~solid[:,0]]=0
    above*=255;above+=.5;np.floor(above,out=above);np.clip(above,0,255,out=above)
    out[:]=above


def _sample_encode(source,uv,factors):
    """Sample and encode a whole batch of pixels, one cache-sized block at a time."""
    count=len(uv);height,width=source.shape[:2]
    flat=source.reshape(-1,4);u=uv[:,0];v=uv[:,1]
    out=np.empty((count,4),dtype=np.uint8)
    for start in range(0,count,_SAMPLE_BLOCK):
        stop=min(count,start+_SAMPLE_BLOCK)
        _sample_block(flat,width,height,u[start:stop],v[start:stop],
                      None if factors is None else factors[start:stop],out[start:stop])
    return out


def _render_planar_scene(canvas,prepared,surfaces,movement,scale,origin_x,origin_y,size,
                         *, progress=0., options=None):
    """Batch exact PMA sampling; retain slot order and reference fallbacks."""
    templates=prepared.setdefault('_preview_planar_templates',{})
    texture_cache=_texture_cache(prepared)
    jobs=[];groups={};walls=[]
    for surface in surfaces:
        if not surface.get('visible',True):continue
        tint=_surface_tint(surface)
        if tint[3]<=0:continue
        values=surface['vertices'];uv=surface['uvs']
        if len(values)!=len(uv) or len(values)%2 or len(values)<6:
            raise ValueError('Mesh positions and UVs must contain matching XY pairs.')
        world=transform_vertices_for_motion(values,movement,progress,options)
        points=[(origin_x+world[i]*scale,origin_y-world[i+1]*scale) for i in range(0,len(world),2)]
        texture=prepared[surface['path']]
        if (surface.get('kind')=='edge' and surface.get('irregular') and len(points)==4 and
                surface.get('hull')==4 and surface.get('triangles')==[0,1,2,2,3,0]):
            walls.append({'surface':surface,'points':points,'uv':uv,'texture':texture,'tint':tint,'job_index':len(jobs)})
            jobs.append(None)
            continue
        template=_planar_template(surface,templates)
        job=_planar_job(texture,points,template,size,tint)
        if job is False:
            rendered=_triangle_patch(texture,points,uv,_triangles(surface,len(points)),size,tint,texture_cache)
            if rendered is not None:jobs.append({'reference':rendered})
        elif job is not None:
            jobs.append(job)
    wall_results=_wall_jobs(walls,size)
    for index,item in enumerate(walls):
        job=wall_results[index]
        if job is False:
            template=_planar_template(item['surface'],templates)
            job=_planar_job(item['texture'],item['points'],template,size,item['tint'])
            if job is False:
                rendered=_triangle_patch(item['texture'],item['points'],item['uv'],item['surface']['triangles'],size,item['tint'],texture_cache)
                job={'reference':rendered} if rendered is not None else None
        jobs[item['job_index']]=job
    jobs=[job for job in jobs if job is not None]
    for job in jobs:
        if 'reference' not in job:groups.setdefault(id(job['texture']),[]).append(job)
    for same_texture in groups.values():
        counts=[len(job['xx']) for job in same_texture]
        coordinates=np.concatenate([job['uv'] for job in same_texture])
        tints=np.asarray([job['tint'] for job in same_texture],dtype=np.float64)
        factors=None
        if not np.all(tints==1.):
            factors=np.repeat(np.column_stack((tints[:,:3]*tints[:,3:4],tints[:,3])),counts,axis=0)
        encoded=_sample_encode(_texture_pma(same_texture[0]['texture'],texture_cache),coordinates,factors)
        offset=0
        for job,count in zip(same_texture,counts):
            job['encoded']=encoded[offset:offset+count];offset+=count
            job['opaque']=bool(np.all(job['encoded'][:,3]==255))
    # Painter-order layers are merged while that cannot change a pixel: an
    # opaque piece replaces whatever is pending beneath it, and a translucent
    # piece joins the pending layer only where nothing has been written yet.
    # A translucent piece over pending pixels composites the layer first.
    width,height=size
    layer=np.zeros((height,width,4),dtype=np.uint8)
    written=np.zeros((height,width),dtype=bool)
    box=None
    def flush():
        nonlocal box
        if box is None:return
        left,top,right,bottom=box
        canvas.alpha_composite(Image.fromarray(layer[top:bottom,left:right]),(left,top))
        layer[top:bottom,left:right]=0;written[top:bottom,left:right]=False;box=None
    for job in jobs:
        if 'reference' in job:
            flush();piece,position=job['reference'];canvas.alpha_composite(piece,position);continue
        if not job['opaque']:
            if not np.any(job['encoded'][:,3]):continue
            if box is not None and written[job['yy'],job['xx']].any():flush()
        layer[job['yy'],job['xx']]=job['encoded'];written[job['yy'],job['xx']]=True
        box=((job['left'],job['top'],job['right'],job['bottom']) if box is None else
             (min(box[0],job['left']),min(box[1],job['top']),max(box[2],job['right']),max(box[3],job['bottom'])))
    flush()
    return canvas


def _spin_reference_scene(options, width, height):
    """A fixed, unit-scale envelope for the extra in-plane turn.

    The full diagonal must fit even for a very wide or tall picture. Keep
    exported base scale and virtual camera magnification visibly adjustable,
    just as the existing preview does, instead of refitting every frame.
    """
    if getattr(options, "model", "extrusion") == "diamond":
        from spine_turn_diamond import diamond_rotation_bounds
        bounds = diamond_rotation_bounds(options, width, height)
        radius = math.hypot(max(abs(bounds["left"]), abs(bounds["right"])),
                            max(abs(bounds["bottom"]), abs(bounds["top"])))
        if options.diamond_sparkles_enabled:
            radius += math.sqrt(2) * min(width, height) * .075
    else:
        depth = options.thickness * options.z_scale
        if options.z_bounce_enabled:
            depth *= max(1, options.peak_z_scale)
        radius = math.sqrt(width * width + height * height + depth * depth) / 2
    radius = max(1., radius)
    if not options.bounce_enabled:
        return 2 * radius, -radius, radius
    anticipation = min(.06, options.landing_squash * .5)
    scale_x = max(1 + options.landing_squash, options.peak_scale)
    scale_y = max(1 + anticipation, 1 + options.landing_squash * .3, options.peak_scale)
    # Y translation stays above the rotating child. Ground compensation uses
    # the original image height, while the rotated geometry uses its diagonal.
    bottom = -radius * scale_y - height * options.landing_squash / 2
    top = options.bounce_height + radius * scale_y + height * max(0., scale_y - 1) / 2
    return 2 * radius * scale_x, bottom, top


def render_pose(prepared, options, angle, size=(720, 600), background="checker", *,
                progress=None, animation_name="rotate_loop", zoom=1.0, show_ground=True, camera=None,
                raster_mode='auto'):
    if raster_mode not in ('auto','reference','fast'):
        raise ValueError('Unknown preview raster mode.')
    width, height = size
    canvas = _canvas(size, background)
    object_width, object_height = prepared["width"], prepared["height"]
    if progress is None:
        start, end = {"flip_to_back": (0, 180), "flip_to_front": (180, 360)}.get(animation_name, (0, 360))
        progress = min(1, max(0, (angle-start)/(end-start)))
    movement = motion_at(progress, options, object_height)
    # Fit a unit-base reference scene. Export base scale remains visibly adjustable;
    # view zoom changes only the camera and never affects the exported skeleton.
    air_scale = options.peak_scale if options.bounce_enabled else 1
    is_diamond = getattr(options, "model", "extrusion") == "diamond"
    depth_extent = ((object_width * options.diamond_waist_width) if is_diamond else options.thickness)
    depth_extent *= getattr(options, "z_scale", 1) * max(1, getattr(options, "peak_z_scale", 1))
    vertical_depth = (depth_extent * abs(math.sin(math.radians(options.diamond_view_tilt)))
                      if is_diamond and options.axis == "y" else depth_extent)
    ground = -object_height / 2
    peak = (options.bounce_height + object_height * (air_scale-.5)) if options.bounce_enabled else object_height/2
    top = max(object_height/2, peak) + vertical_depth/2
    bottom = ground - vertical_depth/2
    reference_width = (max(object_width, depth_extent) if is_diamond else object_width + depth_extent)
    reference_width *= max(1, air_scale) * (1 + (options.landing_squash if options.bounce_enabled else 0))
    if is_diamond and (getattr(options, "diamond_table_depth", 0) or
                       getattr(options, "diamond_waist_depth", 0) or
                       getattr(options, "diamond_ring_phase", 0)):
        from spine_turn_diamond import diamond_rotation_bounds
        bounds = diamond_rotation_bounds(options, object_width, object_height)
        reference_width = max(object_width, 2 * abs(bounds["left"]), 2 * abs(bounds["right"]))
        reference_width *= max(1, air_scale) * (1 + (options.landing_squash if options.bounce_enabled else 0))
        top, bottom = max(object_height / 2, bounds["top"]), min(-object_height / 2, bounds["bottom"])
        if options.bounce_enabled:
            top = max(top, options.bounce_height + top * max(1, air_scale) + object_height * max(0, air_scale - 1) / 2)
            bottom *= max(1, air_scale)
    if getattr(options, "z_spin_enabled", False) and camera is None:
        reference_width, bottom, top = _spin_reference_scene(options, object_width, object_height)
    scale = min(width*.82/max(1, reference_width), height*.82/max(1, top-bottom)) * zoom
    origin_x, origin_y = width/2, height/2 + (top+bottom)/2*scale
    if camera is not None:
        scale = float(camera["scale"]) * zoom
        origin_x, origin_y = float(camera["origin_x"]), float(camera["origin_y"])
    if show_ground and options.bounce_enabled and background != "transparent":
        initial = motion_at(0, options, object_height)
        ground_y = origin_y - (initial["y"] - object_height*initial["scale_y"]/2)*scale
        ImageDraw.Draw(canvas).line((20, ground_y, width-20, ground_y), fill=(96, 111, 135, 255), width=1)
    # Light cells that cannot add a pixel are never built; drawn ones are unchanged.
    surfaces = ordered_surfaces(animation_pose_at(progress, options, object_width, object_height, animation_name,
                                                  cull_hidden_effects=True))
    if raster_mode=='fast' or (raster_mode=='auto' and any(surface.get('irregular') for surface in surfaces)):
        return _render_planar_scene(canvas,prepared,surfaces,movement,scale,origin_x,origin_y,size,
                                    progress=progress,options=options)
    texture_cache = _texture_cache(prepared)
    # A beveled solid joins several materials along the same projected edges.
    # Use one pixel-center coverage convention for the entire solid, including
    # its side strips, so Pillow's polygon coverage cannot disagree at joins.
    triangle_scene = any(surface.get('kind') in ('bevel', 'diamond_face', 'diamond_fx') or surface.get('irregular') for surface in surfaces)
    for surface in surfaces:
        if not surface.get("visible", True):
            continue
        tint = _surface_tint(surface)
        if tint[3] <= 0:
            continue
        texture = prepared[surface["path"]]
        vertices = surface["vertices"]
        uv = surface["uvs"]
        if len(vertices) != len(uv) or len(vertices) % 2 or len(vertices) < 6:
            raise ValueError('Mesh positions and UVs must contain matching XY pairs.')
        world = transform_vertices_for_motion(vertices, movement, progress, options)
        points = [(origin_x + world[i] * scale, origin_y - world[i+1] * scale)
                  for i in range(0, len(world), 2)]
        triangles = _triangles(surface, len(points))
        if triangle_scene or not _affine_quad(points, uv, triangles):
            rendered = _triangle_patch(texture, points, uv, triangles, size, tint, texture_cache)
            if rendered is not None:
                piece, position = rendered
                canvas.alpha_composite(piece, position)
            continue
        # Preserve the fast Pillow affine path for ordinary parallelogram quads.
        p0, p1, p3 = points[0], points[1], points[3]
        ax, ay = p1[0] - p0[0], p1[1] - p0[1]
        bx, by = p3[0] - p0[0], p3[1] - p0[1]
        det = ax * by - ay * bx
        if abs(det) < .00001:
            continue
        left, top = max(0, math.floor(min(x for x, _ in points))), max(0, math.floor(min(y for _, y in points)))
        right, bottom = min(width, math.ceil(max(x for x, _ in points))), min(height, math.ceil(max(y for _, y in points)))
        if right <= left or bottom <= top:
            continue
        iu, iv = by / det, -bx / det
        ju, jv = -ay / det, ax / det
        du, dv = (uv[2] - uv[0]) * texture.width, (uv[3] - uv[1]) * texture.height
        eu, ev = (uv[6] - uv[0]) * texture.width, (uv[7] - uv[1]) * texture.height
        origin_u = uv[0] * texture.width
        origin_v = uv[1] * texture.height
        coeff = (du * iu + eu * ju, du * iv + eu * jv,
                 origin_u + (du * iu + eu * ju) * (left - p0[0]) + (du * iv + eu * jv) * (top - p0[1]),
                 dv * iu + ev * ju, dv * iv + ev * jv,
                 origin_v + (dv * iu + ev * ju) * (left - p0[0]) + (dv * iv + ev * jv) * (top - p0[1]))
        piece = texture.transform((right-left, bottom-top), Image.Transform.AFFINE,
                                  coeff, Image.Resampling.BILINEAR)
        if tint != (1., 1., 1., 1.):
            piece = Image.merge('RGBA', tuple(channel.point(lambda value, factor=factor: round(value * factor))
                for channel, factor in zip(piece.split(), tint)))
        mask = Image.new("L", piece.size, 0)
        ImageDraw.Draw(mask).polygon([(x-left, y-top) for x, y in points], fill=255)
        # Composite via the polygon coverage without multiplying source alpha twice.
        piece.putalpha(ImageChops.multiply(piece.getchannel("A"), mask))
        canvas.alpha_composite(piece, (left, top))
    return canvas
