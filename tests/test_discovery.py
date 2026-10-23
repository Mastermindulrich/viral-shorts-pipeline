import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
import pipeline as p

class DiscoveryTests(unittest.TestCase):
    def test_feed_404_falls_back_to_api(self):
        result=[dict(id='example',title='Example',published='2026-01-01')]
        with patch.object(p.urllib.request,'urlopen',side_effect=HTTPError('url',404,'Not Found',None,None)), patch.object(p,'api_recent_uploads',return_value=result) as fallback:
            self.assertEqual(p.recent_uploads('channel'),result)
            fallback.assert_called_once_with('channel')

    def test_upload_playlist_parsing(self):
        service=MagicMock()
        service.channels.return_value.list.return_value.execute.return_value={'items':[{'contentDetails':{'relatedPlaylists':{'uploads':'UUexample'}}}]}
        service.playlistItems.return_value.list.return_value.execute.return_value={'items':[{'snippet':{'title':'Test','publishedAt':'2026-01-01'},'contentDetails':{'videoId':'example','videoPublishedAt':'2026-01-02'}}]}
        self.assertEqual(p.api_recent_uploads('channel',service),[{'id':'example','title':'Test','published':'2026-01-02'}])
        service.playlistItems.return_value.list.assert_called_once_with(part='snippet,contentDetails',playlistId='UUexample',maxResults=15)

    def test_fallback_failure_retains_both_errors(self):
        with patch.object(p.urllib.request,'urlopen',side_effect=HTTPError('url',404,'Not Found',None,None)), patch.object(p,'api_recent_uploads',side_effect=ValueError('Missing scope')):
            with self.assertRaisesRegex(RuntimeError,'API fallback: Missing scope'):
                p.recent_uploads('channel')
