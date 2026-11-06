import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from utils.compare_locations import (
    _build_object_label,
    build_location_changes,
    filter_changes,
    resolve_classic_radius,
    resolve_user_tokens,
)


def _entry(uid, lat, lon, radius, name=None):
    return {
        'id': uid,
        'name': name or f'Member {uid}',
        'lat': lat,
        'lon': lon,
        'radius': radius,
    }


class BuildLocationChangesTests(unittest.TestCase):
    def setUp(self):
        self.baseline = [
            _entry(1, '48.0000', '11.0000', 1000),
            _entry(2, '48.0000', '11.0000', 1000),
            _entry(3, '48.0000', '11.0000', 1000),
        ]
        self.current = [
            _entry(1, '48.0010', '11.0000', 1100),
            _entry(2, '48.0000', '11.0000', 1000),
            _entry(4, '48.0000', '11.0000', 1000),
        ]
        self.raw_members = {
            '1': {'location': '85560 Ebersberg'},
            '2': {'location': 'Irgendwo'},
            '3': {'location': 'Entfernt'},
            '4': {'location': 'Neu'},
        }
        self.details = {
            '1': {
                'query_variant': 'city_postcode',
                'type': 'boundary',
                'addresstype': 'town',
                'display_name': 'Ebersberg, Bayern',
            }
        }

    def test_summary_counts(self):
        summary, _ = build_location_changes(
            self.baseline,
            self.current,
            raw_members=self.raw_members,
            details=self.details,
        )
        self.assertEqual(summary['baseline'], 3)
        self.assertEqual(summary['current'], 3)
        self.assertEqual(summary['changed'], 1)
        self.assertEqual(summary['added'], 1)
        self.assertEqual(summary['removed'], 1)
        self.assertEqual(summary['unchanged'], 1)

    def test_changed_entry_contains_details_and_distance(self):
        _, changes = build_location_changes(
            self.baseline,
            self.current,
            raw_members=self.raw_members,
            details=self.details,
        )
        changed = next(item for item in changes if item['id'] == '1')
        self.assertEqual(changed['status'], 'changed')
        self.assertEqual(changed['location'], '85560 Ebersberg')
        self.assertEqual(changed['new_addresstype'], 'town')
        self.assertGreater(changed['distance_m'], 100)
        self.assertEqual(changed['radius_delta_m'], 100.0)

    def test_changes_are_sorted_by_distance(self):
        _, changes = build_location_changes(
            self.baseline,
            self.current,
            raw_members=self.raw_members,
            details=self.details,
        )
        self.assertEqual(changes[0]['id'], '1')
        self.assertEqual(
            {item['id'] for item in changes},
            {'1', '3', '4'},
        )

    def test_min_distance_filters_small_changes(self):
        summary, changes = build_location_changes(
            self.baseline,
            self.current,
            raw_members=self.raw_members,
            details=self.details,
            min_distance=200,
        )
        self.assertEqual(summary['changed'], 0)
        self.assertEqual({item['id'] for item in changes}, {'3', '4'})


class LocationSignalTests(unittest.TestCase):
    def test_new_marker_outside_old_radius(self):
        baseline = [_entry(1, '48.0000', '11.0000', 50)]
        current = [_entry(1, '48.0010', '11.0000', 50)]

        summary, changes = build_location_changes(baseline, current)

        item = changes[0]
        self.assertTrue(item['outside_old_radius'])
        self.assertTrue(item['areas_disjoint'])
        self.assertEqual(summary['outside_old_radius'], 1)
        self.assertEqual(summary['areas_disjoint'], 1)

    def test_radius_growth_uses_derived_classic_radius(self):
        baseline = [_entry(1, '48.0000', '11.0000', 1000)]
        current = [_entry(1, '48.0000', '11.0000', 1000)]

        summary, changes = build_location_changes(
            baseline,
            current,
            classic_radii={'1': 2000},
        )

        item = changes[0]
        self.assertEqual(item['radius_basis'], 'derived')
        self.assertEqual(item['effective_radius_m'], 2000)
        self.assertEqual(item['radius_map_delta_m'], 0)
        self.assertEqual(item['radius_delta_m'], 1000)
        self.assertTrue(item['radius_grew'])
        self.assertEqual(summary['radius_grew'], 1)

    def test_formula_only_radius_change_is_unchanged(self):
        baseline = [_entry(1, '48.0000', '11.0000', 6352)]
        current = [_entry(1, '48.0000', '11.0000', 7680)]

        summary, changes = build_location_changes(
            baseline,
            current,
            classic_radii={'1': 6352},
        )

        self.assertEqual(summary['changed'], 0)
        self.assertEqual(summary['unchanged'], 1)
        self.assertEqual(changes, [])

    def test_radius_basis_derived_without_value_is_not_comparable(self):
        baseline = [_entry(1, '48.0000', '11.0000', 1000)]
        current = [_entry(1, '48.0010', '11.0000', 1001)]

        summary, changes = build_location_changes(
            baseline,
            current,
            radius_basis='derived',
        )

        item = changes[0]
        self.assertEqual(item['radius_basis'], 'unavailable')
        self.assertIsNone(item['effective_radius_m'])
        self.assertTrue(item['radius_not_comparable'])
        self.assertFalse(item['radius_grew'])
        self.assertEqual(summary['radius_not_comparable'], 1)

    def test_radius_basis_map_ignores_derived_value(self):
        baseline = [_entry(1, '48.0000', '11.0000', 1000)]
        current = [_entry(1, '48.0000', '11.0000', 1100)]

        _, changes = build_location_changes(
            baseline,
            current,
            radius_basis='map',
            classic_radii={'1': 2000},
        )

        item = changes[0]
        self.assertEqual(item['radius_basis'], 'map')
        self.assertEqual(item['radius_classic_m'], 2000)
        self.assertEqual(item['effective_radius_m'], 1100)
        self.assertEqual(item['radius_delta_m'], 100)

    def test_guard_fallback_is_reported_as_guarded(self):
        baseline = [_entry(1, '48.0000', '11.0000', 1000)]
        current = [_entry(1, '48.0000', '11.0000', 1000)]
        details = {
            '1': {
                'strategy': 'classic_fallback',
                'guard': 'old-radius',
                'guard_distance_m': 5000.0,
                'guard_old_radius_m': 1000,
                'rejected_precision': {
                    'query_variant': 'name',
                    'type': 'village',
                    'addresstype': 'village',
                    'display_name': 'Wrong village',
                },
            }
        }

        summary, changes = build_location_changes(
            baseline,
            current,
            details=details,
            classic_radii={'1': 1000},
        )

        item = changes[0]
        self.assertEqual(item['status'], 'guarded')
        self.assertTrue(item['precision_rejected'])
        self.assertIn('precision_rejected', item['flags'])
        self.assertEqual(item['guard_distance_m'], 5000.0)
        self.assertEqual(item['rejected_display_name'], 'Wrong village')
        self.assertEqual(summary['guarded'], 1)
        self.assertEqual(summary['precision_rejected'], 1)
        self.assertEqual(filter_changes(changes, 'rejected'), changes)

    def test_filter_changes(self):
        changes = [
            {
                'id': '1', 'areas_disjoint': True, 'outside_old_radius': True,
                'radius_grew': False, 'radius_shrank': False,
            },
            {
                'id': '2', 'areas_disjoint': False, 'outside_old_radius': False,
                'radius_grew': True, 'radius_shrank': False,
            },
            {
                'id': '3', 'areas_disjoint': False, 'outside_old_radius': False,
                'radius_grew': False, 'radius_shrank': True,
            },
            {
                'id': '4', 'areas_disjoint': False, 'outside_old_radius': False,
                'radius_grew': False, 'radius_shrank': False,
            },
            {
                'id': '5', 'areas_disjoint': True, 'outside_old_radius': True,
                'radius_grew': False, 'radius_shrank': True,
                'precision_rejected': False,
            },
        ]
        for item in changes:
            item.setdefault('precision_rejected', False)
        self.assertEqual(len(filter_changes(changes, 'all')), 5)
        self.assertEqual(len(filter_changes(changes, 'suspicious')), 3)
        self.assertEqual(
            [c['id'] for c in filter_changes(changes, 'outside-old-radius')],
            ['1', '5'],
        )
        self.assertEqual([c['id'] for c in filter_changes(changes, 'radius-grew')], ['2'])
        self.assertEqual([c['id'] for c in filter_changes(changes, 'radius-shrank')], ['3'])
        self.assertEqual([c['id'] for c in filter_changes(changes, 'improvements')], ['3'])


class ResolveClassicRadiusTests(unittest.TestCase):
    def test_prefers_direct_detail_value(self):
        self.assertEqual(
            resolve_classic_radius({}, {'radius_classic': 1234}),
            1234.0,
        )

    def test_uses_bbox_from_cache_candidate(self):
        detail = {
            'query_variant': 'city_postcode',
            'countrycodes': 'de',
            'osm_type': 'relation',
            'osm_id': 929913,
        }
        candidate = {
            'osm_type': 'relation',
            'osm_id': 929913,
            'boundingbox': ['48.0479114', '48.1243068', '11.9194784', '12.0463161'],
        }

        def cache_get(key):
            return [candidate]

        radius = resolve_classic_radius(
            {'location': '85560 Ebersberg'},
            detail,
            cache_get=cache_get,
        )
        self.assertAlmostEqual(radius, 6352, delta=2)

    def test_returns_none_without_cache_or_details(self):
        self.assertIsNone(resolve_classic_radius({}, {}))


class ObjectLabelTests(unittest.TestCase):
    def test_ebersberg_label_ignores_misleading_municipality(self):
        detail = {
            'name': 'Ebersberg',
            'addresstype': 'town',
            'address': {
                'town': 'Ebersberg',
                'municipality': 'Baiern (VGem Glonn)',
                'county': 'Landkreis Ebersberg',
                'state': 'Bayern',
                'country': 'Deutschland',
            },
        }
        self.assertEqual(
            _build_object_label(detail),
            'Ebersberg (town), Landkreis Ebersberg, Bayern',
        )

    def test_postcode_label(self):
        detail = {
            'name': '14109',
            'addresstype': 'postcode',
            'address': {
                'suburb': 'Wannsee',
                'borough': 'Steglitz-Zehlendorf',
                'city': 'Berlin',
                'country': 'Deutschland',
            },
        }
        self.assertEqual(
            _build_object_label(detail),
            '14109 (postcode), Wannsee, Steglitz-Zehlendorf, Berlin',
        )

    def test_state_label_includes_country(self):
        detail = {
            'name': 'Florida',
            'addresstype': 'state',
            'address': {'state': 'Florida', 'country': 'United States'},
        }
        self.assertEqual(
            _build_object_label(detail),
            'Florida (state), United States',
        )


class ResolveUserTokensTests(unittest.TestCase):
    def setUp(self):
        self.raw = {
            '1': {'uid': '1', 'name': 'Alice'},
            '2': {'uid': '2', 'name': 'Bob'},
            '3': {'uid': '3', 'name': 'Bob'},
        }
        self.baseline = [_entry(1, '48.0', '11.0', 100)]
        self.current = [_entry(1, '48.0', '11.0', 100)]

    def test_resolves_uid_and_name(self):
        self.assertEqual(
            resolve_user_tokens(['1', 'alice'], self.raw, self.baseline, self.current),
            ['1'],
        )

    def test_ambiguous_name_raises(self):
        with self.assertRaises(SystemExit):
            resolve_user_tokens(['bob'], self.raw, self.baseline, self.current)

    def test_unknown_name_raises(self):
        with self.assertRaises(SystemExit):
            resolve_user_tokens(['nobody'], self.raw, self.baseline, self.current)

    def test_include_uids_keeps_unchanged_entry(self):
        summary, changes = build_location_changes(
            self.baseline,
            self.current,
            include_uids={'1'},
        )
        self.assertEqual(summary['unchanged'], 1)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['id'], '1')
        self.assertEqual(changes[0]['status'], 'unchanged')


if __name__ == '__main__':
    unittest.main()
