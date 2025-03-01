# Copyright © 2007-2019 Red Hat, Inc. and others.
#
# This file is part of Bodhi.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""This test suite contains tests for bodhi.server.__init__."""
from unittest import mock
import collections

from pyramid import testing

from bodhi import server
from bodhi.server import models
from bodhi.server.config import config
from bodhi.server.views import generic

from . import base


class TestExceptionFilter:
    """Test the exception_filter() function."""
    @mock.patch('bodhi.server.log.exception')
    def test_exception(self, exception):
        """An Exception should be logged and returned."""
        request_response = OSError('Your money is gone.')

        # The second argument is not used.
        response = server.exception_filter(request_response, None)

        assert response == request_response
        exception.assert_called_once_with(
            "Unhandled exception raised:  {}".format(repr(request_response)))

    @mock.patch('bodhi.server.log.exception')
    def test_no_exception(self, exception):
        """A non-exception should not be logged and should be returned."""
        request_response = 'Your money is safe with me.'

        # The second argument is not used.
        response = server.exception_filter(request_response, None)

        assert response == request_response
        assert exception.call_count == 0


class TestGetBuildinfo:
    """Test get_buildinfo()."""
    def test_get_buildinfo(self):
        """get_buildinfo() should return an empty defaultdict."""
        # The argument isn't used, so we'll just pass None.
        bi = server.get_buildinfo(None)

        assert isinstance(bi, collections.defaultdict)
        assert bi == {}
        assert bi['made_up_key'] == {}


class TestGetCacheregion:
    """Test get_cacheregion()."""
    @mock.patch.dict('bodhi.server.bodhi_config', {'some': 'config'}, clear=True)
    @mock.patch('bodhi.server.make_region')
    def test_get_cacheregion(self, make_region):
        """Test get_cacheregion."""
        # The argument (request) doesn't get used, so we'll just pass None.
        region = server.get_cacheregion(None)

        make_region.assert_called_once_with()
        assert region is make_region.return_value
        region.configure_from_config.assert_called_once_with({'some': 'config'}, 'dogpile.cache.')


class TestGetKoji:
    """Test get_koji()."""
    @mock.patch('bodhi.server.buildsys.get_session')
    def test_get_koji(self, get_session):
        """Ensure that get_koji() returns the response from buildsys.get_session()."""
        # The argument is not used, so set it to None.
        k = server.get_koji(None)

        assert k is get_session.return_value


class TestGetReleases(base.BasePyTestCase):
    """Test the get_releases() function."""
    def test_get_releases(self):
        """Assert correct return value from get_releases()."""
        request = testing.DummyRequest(user=base.DummyUser('guest'))

        releases = server.get_releases(request)

        assert releases == models.Release.all_releases()


class TestMain(base.BasePyTestCase):
    """
    Assert correct behavior from the main() function.
    """
    def test_calls_session_remove(self):
        """Let's assert that main() calls Session.remove()."""
        with mock.patch('bodhi.server.Session.remove') as remove:
            server.main({}, session=self.db, **self.app_settings)

        remove.assert_called_once_with()

    @mock.patch('bodhi.server.bugs.set_bugtracker')
    def test_calls_set_bugtracker(self, set_bugtracker):
        """
        Ensure that main() calls set_bugtracker().
        """
        server.main({}, testing='guest', session=self.db, **self.app_settings)

        set_bugtracker.assert_called_once_with()

    @mock.patch.dict('bodhi.server.config.config', {'test': 'changeme'})
    def test_settings(self):
        """Ensure that passed settings make their way into the Bodhi config."""
        self.app_settings.update({'test': 'setting'})

        server.main({}, testing='guest', session=self.db, **self.app_settings)

        assert config['test'] == 'setting'

    @mock.patch.dict(
        'bodhi.server.config.config',
        {'dogpile.cache.backend': 'dogpile.cache.memory', 'dogpile.cache.expiration_time': 100})
    @mock.patch('bodhi.server.views.generic._generate_home_page_stats', autospec=True)
    def test_sets_up_home_page_cache(self, _generate_home_page_stats):
        """Ensure that the home page cache is configured."""
        _generate_home_page_stats.return_value = 5
        # Let's pull invalidate off of the mock so that main() will decorate it again as a cache.
        del _generate_home_page_stats.invalidate
        assert not hasattr(_generate_home_page_stats, 'invalidate')

        server.main({}, testing='guest', session=self.db)

        # main() should have given it a cache, which would give it an invalidate attribute.
        assert hasattr(generic._generate_home_page_stats, 'invalidate')
        assert generic._generate_home_page_stats() == 5
        # Changing the return value of the mock should not affect the return value since it is
        # cached.
        _generate_home_page_stats.return_value = 7
        assert generic._generate_home_page_stats() == 5
        # If we invalidate the cache, we should see the new return value.
        generic._generate_home_page_stats.invalidate()
        assert generic._generate_home_page_stats() == 7

    def test_warms_up_releases_cache(self):
        """main() should warm up the all_releases cache."""
        # Let's clear the release cache
        config["warm_cache_on_start"] = True
        models.Release.all_releases.cache_clear()

        server.main({}, testing='guest', session=self.db)

        # The cache should have a release in it now - let's just spot check it
        assert models.Release.all_releases()['current'][0]['name'] == 'F17'

    def test_calls_initialize_db(self):
        """main() should call initialize_db() when called without a session arg."""
        with mock.patch('bodhi.server.initialize_db') as init_db:
            server.main({}, **self.app_settings)

        init_db.assert_called_once()
