import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from libs.location_mapping_rules_lib import (
    analyze_location_for_country,
    country_code_candidates,
    order_country_codes,
    prepare_location,
)
from libs.location_precision_lib import (
    build_precision_queries,
    calculate_radius_from_bbox_center,
    calculate_radius_from_point,
    candidate_is_good_enough,
    candidate_matches_location,
    choose_smaller_area,
    extract_place_name,
    postcode_matches,
    precision_cache_key,
    precision_rejection,
    rank_nominatim_candidates,
    summarize_candidate,
)


def _town(name='Ebersberg'):
    return {
        'name': name,
        'type': 'administrative',
        'addresstype': 'town',
        'place_rank': 16,
        'importance': 0.48,
        'address': {'town': name, 'country_code': 'de'},
    }


def _postcode(postcode='85560'):
    return {
        'name': postcode,
        'type': 'postal_code',
        'addresstype': 'postcode',
        'place_rank': 21,
        'importance': 0.12,
        'address': {'postcode': postcode, 'country_code': 'de'},
    }


class ExtractPlaceNameTests(unittest.TestCase):
    def test_removes_postal_code(self):
        self.assertEqual(extract_place_name('85560 ebersberg', '85560', None), 'ebersberg')

    def test_keeps_name_without_postal_code(self):
        self.assertEqual(extract_place_name('ebersberg', None, None), 'ebersberg')

    def test_removes_country_prefix_and_name(self):
        self.assertEqual(extract_place_name('d-85560 ebersberg', '85560', 'de'), 'ebersberg')
        self.assertEqual(
            extract_place_name('85560 ebersberg, deutschland', '85560', 'de'),
            'ebersberg',
        )

    def test_returns_empty_for_postal_code_only(self):
        self.assertEqual(extract_place_name('85560', '85560', None), '')

    def test_keeps_city_name_that_is_also_a_country_alias(self):
        self.assertEqual(extract_place_name('wien', None, 'at'), 'wien')
        self.assertEqual(extract_place_name('wien, österreich', None, 'at'), 'wien')
        self.assertEqual(extract_place_name('new york', None, 'us'), 'new york')


class BuildPrecisionQueriesTests(unittest.TestCase):
    def test_city_and_postcode_first(self):
        queries = build_precision_queries('85560 ebersberg', 'ebersberg', '85560')
        self.assertEqual(queries[0], ('city_postcode', {'city': 'ebersberg', 'postalcode': '85560'}))
        self.assertEqual(queries[1], ('name', {'q': 'ebersberg'}))
        self.assertEqual(queries[2], ('postcode', {'postalcode': '85560'}))
        self.assertEqual(queries[3], ('full', {'q': '85560 ebersberg'}))

    def test_name_only_has_no_duplicate_full_query(self):
        queries = build_precision_queries('ebersberg', 'ebersberg', None)
        self.assertEqual(queries, [('name', {'q': 'ebersberg'})])

    def test_postcode_only(self):
        queries = build_precision_queries('85560', '', '85560')
        self.assertEqual(queries, [('postcode', {'postalcode': '85560'})])


class CountryCodeCandidatesTests(unittest.TestCase):
    def test_four_digit_postcode_tries_belgium(self):
        self.assertEqual(
            country_code_candidates('2490', None),
            ['at,ch', 'be', 'dk,nl', None],
        )

    def test_known_country_is_the_only_candidate(self):
        self.assertEqual(country_code_candidates('2490', 'be'), ['be'])

    def test_five_digit_postcode_keeps_german_priority(self):
        self.assertEqual(
            country_code_candidates('90469', None),
            ['de', 'fr,fi,it', None],
        )

    def test_without_postcode_tries_dach_first(self):
        self.assertEqual(
            country_code_candidates(None, None),
            ['de,at,ch', None],
        )

    def test_preferred_country_code_keeps_fallbacks(self):
        self.assertEqual(
            order_country_codes(
                ['at,ch', 'be', 'dk,nl', None],
                'be',
            ),
            ['be', 'at,ch', 'dk,nl', None],
        )

    def test_unknown_preferred_country_code_keeps_order(self):
        self.assertEqual(
            order_country_codes(['at,ch', 'be', None]),
            ['at,ch', 'be', None],
        )


class RankCandidatesTests(unittest.TestCase):
    def test_prefers_settlement_over_postal_code_area(self):
        result = rank_nominatim_candidates(
            [_postcode(), _town()],
            place_name='ebersberg',
            postal_code='85560',
        )
        self.assertEqual(result['addresstype'], 'town')

    def test_prefers_postal_code_when_no_name_is_known(self):
        result = rank_nominatim_candidates(
            [_town(), _postcode()],
            place_name='',
            postal_code='85560',
        )
        self.assertEqual(result['addresstype'], 'postcode')

    def test_candidate_is_good_enough(self):
        self.assertTrue(candidate_is_good_enough(_town(), place_name='ebersberg'))
        self.assertFalse(candidate_is_good_enough(_postcode(), place_name='ebersberg'))
        self.assertTrue(candidate_is_good_enough(_postcode(), place_name=''))

    def test_rejects_settlement_with_conflicting_postcode_and_name(self):
        saas_balen = _town('Saas-Balen')
        saas_balen['address'] = {'postcode': '3908', 'country_code': 'ch'}

        self.assertFalse(
            candidate_matches_location(saas_balen, 'balen', '2490')
        )
        self.assertFalse(
            candidate_is_good_enough(saas_balen, 'balen', '2490')
        )

    def test_accepts_matching_settlement_without_postcode(self):
        balen = _town('Balen')
        balen['address'] = {'country_code': 'be'}

        self.assertTrue(candidate_matches_location(balen, 'balen', '2490'))
        self.assertTrue(candidate_is_good_enough(balen, 'balen', '2490'))

    def test_name_match_survives_different_postcode(self):
        dahlem = _town('Dahlem')
        dahlem['address'] = {'postcode': '14195', 'country_code': 'de'}

        self.assertTrue(candidate_matches_location(dahlem, 'dahlem', '21368'))
        self.assertTrue(candidate_is_good_enough(dahlem, 'dahlem', '21368'))

    def test_importance_wins_over_lower_place_rank(self):
        country_county = {
            'name': 'Viterbo',
            'type': 'administrative',
            'addresstype': 'county',
            'place_rank': 12,
            'importance': 0.718,
        }
        italian_city = {
            'name': 'Viterbo',
            'type': 'administrative',
            'addresstype': 'city',
            'place_rank': 16,
            'importance': 0.611,
        }
        colombian_town = {
            'name': 'Viterbo',
            'type': 'administrative',
            'addresstype': 'town',
            'place_rank': 12,
            'importance': 0.361,
        }

        result = rank_nominatim_candidates(
            [country_county, italian_city, colombian_town],
            place_name='viterbo',
            postal_code=None,
        )
        self.assertEqual(result['addresstype'], 'city')

    def test_name_matching_ignores_diacritics(self):
        german_village = {
            'name': 'Brügge',
            'type': 'administrative',
            'addresstype': 'village',
            'place_rank': 16,
            'importance': 0.496,
        }
        swiss_locality = {
            'name': 'Brugge',
            'type': 'node',
            'addresstype': 'locality',
            'place_rank': 25,
            'importance': 0.067,
        }

        result = rank_nominatim_candidates(
            [german_village, swiss_locality],
            place_name='brugge',
            postal_code=None,
        )
        self.assertEqual(result['name'], 'Brügge')


class PrecisionCacheKeyTests(unittest.TestCase):
    def test_differs_from_classic_key(self):
        classic_key = ('nominatim', '85560 ebersberg', 'de')
        precision_key = precision_cache_key(
            'city_postcode',
            {'city': 'ebersberg', 'postalcode': '85560'},
            'de',
            'precision-v1',
        )
        self.assertNotEqual(classic_key, precision_key)
        self.assertEqual(precision_key[1], 'precision-v1')

    def test_parameter_order_does_not_change_key(self):
        first = precision_cache_key(
            'city_postcode', {'city': 'ebersberg', 'postalcode': '85560'}, 'de', 'v',
        )
        second = precision_cache_key(
            'city_postcode', {'postalcode': '85560', 'city': 'ebersberg'}, 'de', 'v',
        )
        self.assertEqual(first, second)


class RadiusFromPointTests(unittest.TestCase):
    def test_uses_marker_instead_of_bounding_box_center(self):
        # Ebersberg town: the stored marker is about 1.3 km from the bbox center,
        # so the marker-relative radius is larger than the old half-diagonal.
        radius = calculate_radius_from_point(
            ['48.0479114', '48.1243068', '11.9194784', '12.0463161'],
            '48.0782763',
            '11.9694372',
        )
        self.assertAlmostEqual(radius, 7680, delta=2)

    def test_missing_input_returns_na(self):
        self.assertEqual(calculate_radius_from_point(None, '48.0', '11.0'), 'N/A')
        self.assertEqual(calculate_radius_from_point(['1', '2', '3', '4'], None, '11.0'), 'N/A')

    def test_classic_radius_uses_bbox_center(self):
        radius = calculate_radius_from_bbox_center(
            ['48.0479114', '48.1243068', '11.9194784', '12.0463161']
        )
        self.assertAlmostEqual(radius, 6352, delta=2)

    def test_summary_contains_classic_radius(self):
        summary = summarize_candidate(
            {
                'osm_type': 'relation',
                'osm_id': 929913,
                'type': 'administrative',
                'addresstype': 'town',
                'boundingbox': ['48.0479114', '48.1243068', '11.9194784', '12.0463161'],
            },
            'city_postcode',
            'de',
        )
        self.assertAlmostEqual(summary['radius_classic'], 6352, delta=2)
        self.assertEqual(summary['query_variant'], 'city_postcode')


class AreaRankingTests(unittest.TestCase):
    def test_county_beats_same_named_village(self):
        county = {
            'name': 'Landkreis Ammerland',
            'type': 'administrative',
            'addresstype': 'county',
            'place_rank': 12,
            'importance': 0.514,
        }
        village = {
            'name': 'Ammerland',
            'type': 'village',
            'addresstype': 'village',
            'place_rank': 19,
            'importance': 0.275,
        }

        result = rank_nominatim_candidates(
            [county, village],
            place_name='ammerland',
            postal_code=None,
        )
        self.assertEqual(result['addresstype'], 'county')

    def test_region_beats_same_named_hamlet(self):
        region = {
            'name': 'Pfalz',
            'type': 'region',
            'addresstype': 'region',
            'place_rank': 10,
            'importance': 0.267,
        }
        hamlet = {
            'name': 'Pfalz',
            'type': 'hamlet',
            'addresstype': 'hamlet',
            'place_rank': 20,
            'importance': 0.133,
        }

        result = rank_nominatim_candidates(
            [hamlet, region],
            place_name='pfalz',
            postal_code=None,
        )
        self.assertEqual(result['addresstype'], 'region')

    def test_city_with_parenthetical_suffix_beats_village(self):
        city = {
            'name': 'Frankenthal (Pfalz)',
            'type': 'administrative',
            'addresstype': 'town',
            'place_rank': 12,
            'importance': 0.543,
        }
        village = {
            'name': 'Frankenthal',
            'type': 'village',
            'addresstype': 'village',
            'place_rank': 19,
            'importance': 0.2,
        }

        result = rank_nominatim_candidates(
            [village, city],
            place_name='frankenthal',
            postal_code=None,
        )
        self.assertEqual(result['name'], 'Frankenthal (Pfalz)')


class LocationMappingTests(unittest.TestCase):
    def test_franken_maps_to_bavaria(self):
        self.assertEqual(prepare_location('franken'), 'bayern')
        self.assertEqual(prepare_location('unterfranken'), 'unterfranken')

    def test_south_florida_maps_to_florida(self):
        self.assertEqual(prepare_location('south florida'), 'florida, usa')

    def test_stockholm_is_recognized_as_sweden(self):
        self.assertEqual(analyze_location_for_country('stockholm'), 'se')


class PrecisionRejectionTests(unittest.TestCase):
    def test_rejects_marker_outside_classic_radius(self):
        classic = {
            'lat': '48.0',
            'lon': '11.0',
            'boundingbox': ['47.99', '48.01', '10.99', '11.01'],
        }
        precision = {'lat': '49.0', 'lon': '11.0'}

        rejection = precision_rejection(precision, classic)
        self.assertIsNotNone(rejection)
        self.assertGreater(rejection['distance_m'], rejection['old_radius_m'])

    def test_accepts_marker_inside_classic_radius(self):
        classic = {
            'lat': '48.0',
            'lon': '11.0',
            'boundingbox': ['47.99', '48.01', '10.99', '11.01'],
        }
        precision = {'lat': '48.0005', 'lon': '11.0005'}

        self.assertIsNone(precision_rejection(precision, classic))

    def test_disjoint_mode_tolerates_move_from_tiny_point(self):
        classic = {
            'lat': '48.0',
            'lon': '11.0',
            'boundingbox': ['47.9999', '48.0001', '10.9999', '11.0001'],
        }
        precision = {
            'lat': '48.018',
            'lon': '11.0',
            'boundingbox': ['47.99', '48.046', '10.97', '11.03'],
        }

        self.assertIsNotNone(
            precision_rejection(precision, classic, mode='old-radius')
        )
        self.assertIsNone(
            precision_rejection(precision, classic, mode='disjoint')
        )


class SmallerAreaSelectionTests(unittest.TestCase):
    def setUp(self):
        self.settlement = {
            'name': 'Ebersberg',
            'boundingbox': ['48.0479114', '48.1243068', '11.9194784', '12.0463161'],
        }
        self.postcode = {
            'name': '85560',
            'boundingbox': ['48.0479114', '48.1671456', '11.8399485', '12.0463161'],
        }

    def test_settlement_wins_when_smaller(self):
        chosen, info = choose_smaller_area(self.settlement, self.postcode)
        self.assertIs(chosen, self.settlement)
        self.assertEqual(info['selection'], 'settlement_smaller')

    def test_postcode_wins_when_smaller(self):
        city = {
            'name': 'Berlin',
            'boundingbox': ['52.3', '52.7', '13.0', '13.8'],
        }
        postcode = {
            'name': '14109',
            'boundingbox': ['52.40', '52.44', '13.10', '13.16'],
        }
        chosen, info = choose_smaller_area(city, postcode)
        self.assertIs(chosen, postcode)
        self.assertEqual(info['selection'], 'postcode_smaller')

    def test_equal_radius_prefers_postcode(self):
        settlement = {
            'name': 'Warburg',
            'boundingbox': ['51.4', '51.6', '8.9', '9.2'],
        }
        postcode = {
            'name': '34414',
            'boundingbox': ['51.4', '51.6', '8.9', '9.2'],
        }
        chosen, info = choose_smaller_area(settlement, postcode)
        self.assertIs(chosen, postcode)
        self.assertEqual(info['selection'], 'postcode_smaller')

    def test_missing_postcode_uses_settlement(self):
        chosen, info = choose_smaller_area(self.settlement, None)
        self.assertIs(chosen, self.settlement)
        self.assertEqual(info['selection'], 'only_settlement')

    def test_postcode_matching(self):
        entry = {'name': '85560', 'address': {'postcode': '85560'}}
        self.assertTrue(postcode_matches(entry, '85560'))
        self.assertFalse(postcode_matches(entry, '85561'))


if __name__ == '__main__':
    unittest.main()
