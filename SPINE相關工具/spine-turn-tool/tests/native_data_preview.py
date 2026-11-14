"""Draw verified official-runtime native-binary world geometry with the CPU rasterizer."""
import hashlib
import json
from pathlib import Path

from PIL import Image,ImageDraw

from spine_turn_preview import _triangle_patch
from verify_v14_pipeline import preview_gif


def render_native_pose(pose,textures,camera,size=(512,512)):
    canvas=Image.new('RGBA',size,(0,0,0,0))
    cache={}
    scale=float(camera['scale'])
    ox,oy=float(camera['origin_x']),float(camera['origin_y'])
    for mesh in pose['geometry'].values():
        tint=tuple(mesh['color'])
        if tint[3]<=0:continue
        points=[(ox+x*scale,oy-y*scale) for x,y in zip(mesh['vertices'][::2],mesh['vertices'][1::2])]
        assert mesh['triangles'] and len(mesh['vertices'])==len(mesh['uvs'])
        patch=_triangle_patch(textures[mesh['path']],points,mesh['uvs'],mesh['triangles'],size,tint,cache)
        if patch is not None:
            pixels,position=patch
            canvas.alpha_composite(pixels,position)
    return canvas


def native_delivery_preview(case_folder,destination,options):
    case_folder,destination=Path(case_folder),Path(destination)
    sampled_path=case_folder/'4.0-native-binary-poses.json'
    sampled=json.loads(sampled_path.read_text(encoding='utf-8'))
    assert sampled['data_version']=='4.0.56'
    poses=sampled['animations']['rotate_loop']['poses']
    textures={}
    for path in (case_folder/'spine-4.0/images').glob('*.png'):
        with Image.open(path) as image:textures[path.stem]=image.convert('RGBA')
    sequence_folder=destination/'png-sequence'
    manifest_path=sequence_folder/'sequence.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest['frame_count']==60 and manifest['status']=='complete'
    camera=manifest['camera']

    def pose_at(progress):
        pose=min(poses,key=lambda value:abs(value['progress']-progress))
        assert abs(pose['progress']-progress)<1e-12,(progress,pose['progress'])
        return pose

    frame_hashes=[]
    for index in range(60):
        frame=render_native_pose(pose_at(index/60),textures,camera)
        path=sequence_folder/f'frame_{index:04d}.png'
        frame.save(path)
        frame_hashes.append(hashlib.sha256(frame.tobytes()).hexdigest())
    binary=next((case_folder/'spine-4.0/native-binary').glob('*.skel'))
    provenance=dict(kind='official-runtime-native-binary',spine_version='4.0.56',
        binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        verified_runtime_samples_sha256=hashlib.sha256(sampled_path.read_bytes()).hexdigest(),
        source_project=f'../spine-4.0/{options.name}.spine',
        draw_order='Actual skeleton.drawOrder from official-runtime samples; no source sorting during drawing',
        world_vertices_include_bone_motion=True,rasterizer='Shared Pillow/NumPy triangle rasterizer; not native GPU capture',
        frame_pixel_sha256=frame_hashes)
    manifest['render_source']=provenance
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    preview_gif(sequence_folder,destination/'preview.gif')
    sheet=Image.new('RGB',(4*276,2*304),'#202637')
    draw=ImageDraw.Draw(sheet)
    for cell in range(8):
        progress=cell/8
        image=render_native_pose(pose_at(progress),textures,camera)
        image.thumbnail((256,256),Image.Resampling.LANCZOS)
        x,y=(cell%4)*276+10,(cell//4)*304+12
        for cy in range(0,256,16):
            for cx in range(0,256,16):
                color='#343d50' if (cx+cy)//16%2 else '#283044'
                draw.rectangle((x+cx,y+cy,x+cx+15,y+cy+15),fill=color)
        sheet.paste(image,(x+(256-image.width)//2,y+(256-image.height)//2),image)
        draw.text((x,y+267),f'{progress*options.duration:.2f}s / {progress*360:g} deg',fill='#edf2fa')
    sheet.save(destination/'preview-contact-sheet.png')
    delivery=destination/'delivery.json'
    data=json.loads(delivery.read_text(encoding='utf-8'))
    data['preview_source']=provenance
    delivery.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    return dict(native_binary_rendered_frames=60,frame_size=[512,512],
                binary_sha256=provenance['binary_sha256'],actual_runtime_draw_order_used=True,
                sample_progresses_exact=True)
