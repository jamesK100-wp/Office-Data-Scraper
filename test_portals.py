import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import unittest
from unittest.mock import patch
from portals import allowed, discover, project_links
from enrichment import Page, fetch
import requests
from unittest.mock import Mock

class PortalTests(unittest.TestCase):
    def test_temporary_failure_retried(self):
        with patch('enrichment._fetch_once', side_effect=[requests.Timeout(), ('ok', 'https://www.magicbricks.com/')]) as request, patch('enrichment.time.sleep'):
            self.assertEqual(fetch('https://www.magicbricks.com/')[0], 'ok')
        self.assertEqual(request.call_count, 2)

    def test_access_denials_not_retried(self):
        for status in (403, 429):
            error = requests.HTTPError(response=Mock(status_code=status))
            with patch('enrichment._fetch_once', side_effect=error) as request, patch('enrichment.time.sleep') as sleep:
                with self.assertRaises(requests.HTTPError):
                    fetch('https://www.magicbricks.com/')
                self.assertEqual(request.call_count, 1)
                sleep.assert_not_called()

    def test_retry_limit(self):
        with patch('enrichment._fetch_once', side_effect=requests.Timeout()) as request, patch('enrichment.time.sleep'):
            with self.assertRaises(requests.Timeout):
                fetch('https://www.magicbricks.com/')
        self.assertEqual(request.call_count, 3)

    def test_accessible_portal_survives_other_portal_failure(self):
        directory = Page('<a href="/example-pune-pdpid-123">Example</a>')
        project = Page('<h1>Example Gardens</h1><p>Total Units</p><p>120</p>')
        error = requests.HTTPError(response=Mock(status_code=403))
        with patch('portals.get_page', side_effect=[
                (directory, 'https://www.magicbricks.com/'),
                (project, 'https://www.magicbricks.com/example-pune-pdpid-123'), error]):
            candidates, details, reports = discover('Pune')
        self.assertEqual(len(candidates), 1)
        self.assertEqual(next(iter(details.values()))['fields']['Number of Units'], 120)
        self.assertTrue(any('HTTP 403' in report for report in reports))

    def test_domain_boundary(self):
        self.assertTrue(allowed('https://www.magicbricks.com/a'))
        self.assertTrue(allowed('https://www.99acres.com/a'))
        self.assertFalse(allowed('https://magicbricks.com.evil.test/a'))
        self.assertFalse(allowed('https://housing.com/a'))
    def test_redirect_checked_before_request(self):
        with patch('enrichment.requests.get') as request:
            with self.assertRaises(ValueError):
                fetch('https://housing.com/',allowed=allowed)
            request.assert_not_called()
    def test_no_offsite_discovery(self):
        p=Page('<a href="https://evil.test/pune-pdpid-123">x</a><a href="/demo-pune-pdpid-123">Demo</a>')
        self.assertEqual(project_links(p,'https://www.magicbricks.com/','Pune'),['https://www.magicbricks.com/demo-pune-pdpid-123'])
    def test_blocked_sources_no_fallback(self):
        with patch('portals.get_page',side_effect=ValueError('Blocked')):
            candidates,details,reports=discover('Pune')
        self.assertFalse(candidates)
        self.assertFalse(details)
        self.assertEqual(len(reports),2)

if __name__=='__main__': unittest.main()
