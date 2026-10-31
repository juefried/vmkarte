import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from libs.vehicle_label_lib import (
    VEHICLE_FIELDS,
    VehicleLabelResolver,
    humanize_choice_value,
    load_vehicle_label_map,
    normalize_label,
)


class NormalizeLabelTests(unittest.TestCase):
    def test_normalizes_case_punctuation_and_umlauts(self):
        self.assertEqual(normalize_label('Müller Modell'), 'mueller modell')
        self.assertEqual(normalize_label('DF-XL'), 'df xl')
        self.assertEqual(normalize_label('  M5  26/20  '), 'm5 26 20')
        self.assertEqual(normalize_label('Z&Z Swing'), 'z amp z swing')


class HumanizeChoiceValueTests(unittest.TestCase):
    def test_uses_token_casing(self):
        casing = {'df': 'DF', 'xl': 'XL', 'waw': 'WAW'}
        self.assertEqual(humanize_choice_value('df_xl', casing), 'DF XL')
        self.assertEqual(humanize_choice_value('waw_2', casing), 'WAW 2')

    def test_keeps_unknown_words_title_cased(self):
        self.assertEqual(humanize_choice_value('neues_modell'), 'Neues Modell')

    def test_renders_amp_token(self):
        self.assertEqual(humanize_choice_value('z_amp_z_new'), 'Z & Z New')


class VehicleLabelResolverTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {
            'vm': {
                'df_xl': 'DF XL',
                'after_7': 'After7',
                'go_one_evo_k': 'Go-One Evo K',
            },
            'lr': {
                'm5_carbon_high_racer': 'M5 Carbon High Racer',
                'z_amp_z_swing': 'Z&Z Swing',
            },
            'tr': {
                'azub_t_tris': 'AZUB T-Tris',
            },
        }
        self.resolver = VehicleLabelResolver(self.mapping)

    def test_exact_match(self):
        self.assertEqual(self.resolver.resolve('vm', 'df_xl'), ('DF XL', 1.0, 'exact'))

    def test_normalized_match(self):
        self.assertEqual(self.resolver.resolve('vm', 'df__xl'), ('DF XL', 0.95, 'normalized'))
        self.assertEqual(self.resolver.resolve('vm', 'DF-XL'), ('DF XL', 0.95, 'normalized'))

    def test_token_order_and_punctuation_match(self):
        self.assertEqual(
            self.resolver.resolve('vm', 'go_one_evo_k'),
            ('Go-One Evo K', 1.0, 'exact'),
        )
        self.assertEqual(
            self.resolver.resolve('vm', 'evo_k_go_one'),
            ('Go-One Evo K', 0.92, 'tokens'),
        )

    def test_extension_preserves_extra_tokens(self):
        self.assertEqual(
            self.resolver.resolve('lr', 'm5_carbon_high_racer_2024'),
            ('M5 Carbon High Racer 2024', 0.9, 'extension'),
        )
        self.assertEqual(
            self.resolver.resolve('tr', 'azub_t_tris_2024'),
            ('AZUB T-Tris 2024', 0.9, 'extension'),
        )
        self.assertEqual(
            self.resolver.resolve('lr', 'z_amp_z_swing_2'),
            ('Z&Z Swing 2', 0.9, 'extension'),
        )

    def test_humanized_fallback_uses_known_casing(self):
        self.assertEqual(
            self.resolver.resolve('vm', 'neues_modell'),
            ('Neues Modell', 0.35, 'humanized'),
        )

    def test_display_value_is_kept(self):
        self.assertEqual(
            self.resolver.resolve('vm', 'Custom Model'),
            ('Custom Model', 0.9, 'display'),
        )

    def test_other_field_is_passthrough(self):
        self.assertEqual(
            self.resolver.resolve('other', 'Brompton, Tern HSD'),
            ('Brompton, Tern HSD', 1.0, 'passthrough'),
        )

    def test_is_known(self):
        self.assertTrue(self.resolver.is_known('vm', 'df_xl'))
        self.assertFalse(self.resolver.is_known('vm', 'DF XL'))


class LabelMapLoadingTests(unittest.TestCase):
    def test_missing_map_returns_empty_fields(self):
        mapping = load_vehicle_label_map(Path('does-not-exist.json'))
        self.assertEqual(set(mapping), set(VEHICLE_FIELDS))
        for field in VEHICLE_FIELDS:
            self.assertEqual(mapping[field], {})

    def test_default_map_contains_known_models(self):
        mapping = load_vehicle_label_map()
        self.assertEqual(mapping['vm']['df_xl'], 'DF XL')
        self.assertEqual(mapping['lr']['m5_carbon_high_racer'], 'M5 Carbon High Racer')
        self.assertEqual(mapping['tr']['azub_t_tris'], 'AZUB T-Tris')


if __name__ == '__main__':
    unittest.main()
