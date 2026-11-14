"""Artwork-cut regions preserve geometry while animating independent light."""
from collections import Counter
from dataclasses import replace
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spine_turn_core import TurnOptions, prepare_images, resolve_options, pose_at
from spine_turn_diamond import diamond_geometry
from spine_turn_diamond_cuts import validate_cut_regions, split_diamond_geometry
from spine_turn_project import save_project, load_project

LEFT = ((-.30, -.10), (0., -.10), (0., .28))
RIGHT = ((0., -.10), (.30, -.10), (0., .28))
REGIONS = ((LEFT, -35., -10.), (RIGHT, 35., 15.))


def volume(geometry):
    result = 0.
    for face in geometry:
        model, triangles = face['model'], face['triangles']
        for i in range(0, len(triangles), 3):
            a, b, c = [model[triangles[i + n]] for n in range(3)]
            result += (a[0] * (b[1]*c[2] - b[2]*c[1]) +
                       a[1] * (b[2]*c[0] - b[0]*c[2]) +
                       a[2] * (b[0]*c[1] - b[1]*c[0])) / 6
    return result


class DiamondCutTests(unittest.TestCase):
    def test_regions_reject_overlap_crossing_concavity_unbounded_and_bad_directions(self):
        self.assertEqual(validate_cut_regions(REGIONS), REGIONS)
        reversed_points = tuple(reversed(LEFT))
        self.assertEqual(validate_cut_regions(((reversed_points, -35, -10),)), (REGIONS[0],))
        invalid = (
            ((LEFT, 0, 0), (LEFT, 20, 0)),
            ((((0,0),(.2,.2),(0,.2),(.2,0)), 0, 0),),
            ((((0,0),(.4,0),(.1,.1),(.4,.4),(0,.4)), 0, 0),),
            ((((0,0),(.6,0),(0,.4)), 0, 0),),
            ((LEFT, math.nan, 0),), ((LEFT, 61, 0),),
            ((LEFT, 0, -61),), ((LEFT[:2], 0, 0),),
        )
        for regions in invalid:
            with self.subTest(regions=regions), self.assertRaises(ValueError):
                validate_cut_regions(regions)

    def test_partition_keeps_volume_and_every_edge_shared_twice(self):
        options = TurnOptions(model='diamond')
        for width, height, scale in ((384,384,1.), (466,368,.7), (320,540,1.8)):
            base = diamond_geometry(options, width, height)
            cuts = split_diamond_geometry(base, REGIONS, width, height, 12, scale)
            self.assertAlmostEqual(volume(cuts), volume(base), places=5)
            edges = Counter()
            for face in cuts:
                model, triangles = face['model'], face['triangles']
                for i in range(0, len(triangles), 3):
                    points = [tuple(round(x,6) for x in model[triangles[i + n]]) for n in range(3)]
                    for a,b in zip(points, points[1:] + points[:1]):
                        if math.dist(a,b) > 1e-6:
                            edges[tuple(sorted((a,b)))] += 1
            self.assertEqual(set(edges.values()), {2})
            self.assertTrue(any(face['cut_region'] == 0 for face in cuts))
            self.assertTrue(any(face['cut_region'] == 1 for face in cuts))
            self.assertTrue(any(face['cut_region'] == -1 for face in cuts))
        self.assertIs(split_diamond_geometry(base, (), width,height,12), base)

    def test_direction_changes_tint_without_changing_volume_uvs_visibility_or_vertices(self):
        a = TurnOptions(model='diamond', trim_transparent=False, diamond_cut_regions=REGIONS,
            diamond_shine_enabled=False, diamond_sparkles_enabled=False)
        b = replace(a, diamond_cut_regions=tuple((points, -yaw, -pitch) for points,yaw,pitch in REGIONS))
        prepared = prepare_images(ROOT/'assets/demo-diamond.png', options=a)
        a,b = resolve_options(prepared,a), resolve_options(prepared,b)
        differing = 0
        for angle in (0,33,90,145,180,267,360):
            first,second = pose_at(angle,a,384,384),pose_at(angle,b,384,384)
            self.assertEqual(len(first),len(second))
            for left,right in zip(first,second):
                for key in ('vertices','model_vertices','triangles','uvs','visible','normal'):
                    self.assertEqual(left[key],right[key],key)
                differing += left['color'] != right['color'] and left['visible']
        self.assertGreater(differing,10)
        for start,end in zip(pose_at(0,a,384,384),pose_at(360,a,384,384)):
            self.assertEqual((start['visible'],start['color']), (end['visible'],end['color']))
            self.assertLess(max(abs(x-y) for x,y in zip(start['vertices'],end['vertices'])),1e-9)

    def test_tool_project_embeds_cut_regions_and_original_art(self):
        options=TurnOptions(model='diamond',trim_transparent=False,diamond_cut_regions=REGIONS)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cut.spturn'
            save_project(path, {'front':ROOT/'assets/demo-diamond.png','back':None,'edge':None}, options)
            with load_project(path) as loaded:
                self.assertEqual(loaded.options.diamond_cut_regions,REGIONS)
                source=prepare_images(loaded.paths['front'],options=loaded.options)
                restored=resolve_options(source,loaded.options)
                self.assertTrue(any('cut' in mesh['name'] for mesh in pose_at(45,restored,384,384)))


if __name__=='__main__':
    unittest.main()
