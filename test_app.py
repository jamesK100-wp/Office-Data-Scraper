import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
backend = importlib.import_module('main')


class SearchTests(unittest.TestCase):
    def test_city_export_and_no_cross_city_research(self):
        response = Mock(ok=True)
        response.json.return_value = {'places': [{'id': 'pune-id', 'displayName': {'text': '=Untrusted listing'},
            'formattedAddress': 'Pune, Maharashtra', 'addressComponents': [
                {'types': ['locality'], 'longText': 'Pune'}]}]}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(backend, '__file__', str(Path(directory) / 'main.py')), \
                 patch.object(backend, 'load_api_key', return_value='test'), \
                 patch.object(backend, 'load_project_details', return_value={'mumbai-id': {'fields': {'Builder Name': 'Mumbai builder'}}}), \
                 patch.object(backend.requests, 'post', return_value=response) as post:
                result = backend.main('Pune', interactive=False)
            self.assertEqual(result['count'], 1)
            self.assertEqual(result['researched'], 0)
            self.assertTrue(all('Pune, India' in c.kwargs['json']['textQuery'] for c in post.call_args_list))
            wb = load_workbook(Path(directory) / 'output' / result['file'])
            self.assertEqual(wb['Projects']['A2'].data_type, 's')
            self.assertIsNone(wb['Projects']['C2'].value)
            self.assertEqual(wb['Projects']['G2'].value, 'Pune')
            wb.close()

    def test_bad_city_before_network(self):
        with self.assertRaises(ValueError):
            backend.main('../../config')

    def test_api_error_redacts_key(self):
        response = Mock(ok=False, status_code=403)
        response.json.return_value = {'error': {'message': 'invalid secret-key'}}
        with patch.object(backend, 'load_api_key', return_value='secret-key'), \
             patch.object(backend.requests, 'post', return_value=response):
            with self.assertRaises(SystemExit) as error:
                backend.main('Delhi')
        self.assertNotIn('secret-key', str(error.exception))


if __name__ == '__main__':
    unittest.main()
