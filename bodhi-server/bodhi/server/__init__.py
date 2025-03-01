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
"""Initialize the Bodhi server."""
from collections import defaultdict
import importlib.metadata
import logging as python_logging

from cornice.validators import DEFAULT_FILTERS
from dogpile.cache import make_region
from munch import munchify
from pyramid.config import Configurator
from pyramid.renderers import JSONP
from pyramid.session import JSONSerializer, SignedCookieSessionFactory
from pyramid.tweens import EXCVIEW
from sqlalchemy import engine_from_config, event
from sqlalchemy.orm import scoped_session, sessionmaker
import pkg_resources

from bodhi.server import bugs, buildsys
from bodhi.server.config import config as bodhi_config
from bodhi.server.security import BodhiSecurityPolicy


METADATA = importlib.metadata.metadata('bodhi-server')
__version__ = METADATA['version']


# This is a regular expression used to match username mentions in comments.
MENTION_RE = r'(?<!\S)(@\w+)'

log = python_logging.getLogger(__name__)


#
# Request methods
#

def get_cacheregion(request):
    """
    Return a CacheRegion to be used to cache results.

    Args:
        request (pyramid.request.Request): The current web request. Unused.
    Returns:
        dogpile.cache.region.CacheRegion: A configured CacheRegion.
    """
    region = make_region()
    region.configure_from_config(bodhi_config, "dogpile.cache.")
    return region


def setup_buildsys():
    """Initialize buildsystem instance from bodhi_config."""
    buildsys.setup_buildsystem(bodhi_config)


def get_koji(request):
    """
    Return a Koji client, or a duck-type of a Koji client, depending on config.

    Args:
        request (pyramid.request.Request): The current web request. Unused.
    Returns:
        koji.ClientSession or DevBuildSys: A Koji client, or a dev Koji mock.
    """
    return buildsys.get_session()


def get_buildinfo(request):
    """
    Return a defaultdict, defaulting to dictionary values.

    A per-request cache populated by the validators and shared with the views
    to store frequently used package-specific data, like build tags and ACLs.

    Args:
        request (pyramid.request.Request): The current web request. Unused.
    Returns:
        collections.defaultdict: A cache populated by the validators and used by the views.
    """
    return defaultdict(dict)


def get_from_tag_inherited(request):
    """
    Return a list, defaulting to empty.

    A per-request cache populated by the validators and shared with the views
    to store the list of inherited tags of a sidetag.

    Args:
        request (pyramid.request.Request): The current web request. Unused.
    Returns:
        list: A cache populated by the validators and used by the views.
    """
    return list()


def get_releases(request):
    """
    Return a defaultdict describing all Releases keyed by state.

    Args:
        request (pyramid.request.Request): The current web request. Unused.
    Returns:
        collections.defaultdict: A dictionary mapping release states to a list of JSON strings
            that describe the Releases that are in those states.
    """
    from bodhi.server.models import Release
    return Release.all_releases()


def exception_filter(response, request):
    """
    Log exceptions that get thrown up to cornice.

    Args:
        response (object): The response returned by a request handler.
        request (pyramid.request.Request): The current web request.
    """
    if isinstance(response, Exception):
        log.exception('Unhandled exception raised:  %r' % response)
    return response


DEFAULT_FILTERS.insert(0, exception_filter)


#
# Bodhi initialization
#

#: An SQLAlchemy scoped session with an engine configured using the settings in Bodhi's server
#: configuration file. Note that you *must* call :func:`initialize_db` before you can use this.
Session = scoped_session(sessionmaker())


def initialize_db(config):
    """
    Initialize the database using the given configuration.

    This *must* be called before you can use the :data:`Session` object.

    Args:
        config (dict): The Bodhi server configuration dictionary.

    Returns:
        sqlalchemy.engine: The database engine created from the configuration.
    """
    # The SQLAlchemy database engine. This is constructed using the value of
    # ``DB_URL`` in :data:`config``. Note: A copy is provided since ``engine_from_config``
    # uses ``pop``.
    engine = engine_from_config(config.copy(), 'sqlalchemy.')
    # When using SQLite we need to make sure foreign keys are enabled:
    # http://docs.sqlalchemy.org/en/latest/dialects/sqlite.html#foreign-key-support
    if config['sqlalchemy.url'].startswith('sqlite:'):
        event.listen(
            engine,
            'connect',
            lambda db_con, con_record: db_con.execute('PRAGMA foreign_keys=ON')
        )
    Session.configure(bind=engine)
    return engine


def main(global_config, testing=None, session=None, **settings):
    """
    Return a WSGI application.

    Args:
        global_config (dict): A dictionary with two keys: __file__, a path to the ini file, and
            here, the path to the code.
        testing (str or None): If this app is contructed by the unit tests, they should set this to
            a username.
        session (sqlalchemy.orm.session.Session or None): If given, the session will be used instead
            of building a new one.
        settings (dictionary): Unused.
    Returns:
        pyramid.router.Router: A WSGI app.
    """
    if settings:
        bodhi_config.load_config(settings)

    # Setup our bugtracker and buildsystem
    bugs.set_bugtracker()
    setup_buildsys()

    # Sessions & Caching
    session_factory = SignedCookieSessionFactory(
        bodhi_config['session.secret'],
        serializer=JSONSerializer(),
    )

    # Construct a list of all groups we're interested in
    default = []
    for key in ('important_groups', 'admin_packager_groups', 'mandatory_packager_groups',
                'admin_groups'):
        default.extend(bodhi_config.get(key))
    # pyramid_fas_openid looks for this setting
    bodhi_config['openid.groups'] = bodhi_config.get('openid.groups', default)

    config = Configurator(settings=bodhi_config, session_factory=session_factory)

    # Plugins
    config.include('pyramid_mako')
    config.include('cornice')

    # Lazy-loaded memoized request properties
    if session:
        config.registry.sessionmaker = lambda: session
    else:
        # Initialize the database scoped session
        initialize_db(bodhi_config)
        config.registry.sessionmaker = Session

    config.add_request_method(lambda x: Session, 'db', reify=True)

    config.add_request_method(get_koji, 'koji', reify=True)
    config.add_request_method(get_cacheregion, 'cache', reify=True)
    config.add_request_method(get_buildinfo, 'buildinfo', reify=True)
    config.add_request_method(get_from_tag_inherited, 'from_tag_inherited', reify=True)
    config.add_request_method(get_releases, 'releases', reify=True)

    # Templating
    config.add_mako_renderer('.html', settings_prefix='mako.')
    config.add_static_view(f'static/v{pkg_resources.get_distribution("bodhi-server").version}',
                           'bodhi.server:static')

    from bodhi.server.renderers import rss
    config.add_renderer('rss', rss)
    config.add_renderer('jsonp', JSONP(param_name='callback'))

    # i18n
    config.add_translation_dirs('bodhi.server:locale/')

    # Authentication & Authorization
    if testing:
        # use a permissive security policy while running unit tests
        fake_identity = munchify(
            {'name': testing,
             'email': f'{testing}@bodhi-dev.example.com',
             'groups': [{'name': 'packager'},
                        {'name': 'ipausers'},
                        {'name': 'fedora-contributor'},
                        {'name': 'signed_fpca'},
                        {'name': 'fedorabugs'},],
             'openid': bodhi_config['openid_template'].format(username=testing)}
        )
        config.testing_securitypolicy(userid=testing, identity=fake_identity, permissive=True)
    else:
        timeout = bodhi_config.get('authtkt.timeout')
        config.set_security_policy(BodhiSecurityPolicy(
            bodhi_config['authtkt.secret'], secure=bodhi_config['authtkt.secure'],
            hashalg='sha512', timeout=timeout,
            max_age=timeout, samesite='Strict'))

    # Collect metrics for endpoints
    config.add_tween(
        'bodhi.server.services.metrics_tween.histo_tween_factory', over=EXCVIEW
    )

    # Metrics Route
    config.add_route('prometheus_metric', '/metrics')

    # Frontpage
    config.add_route('home', '/')

    # Views for creating new objects
    config.add_route('new_update', '/updates/new')
    config.add_route('new_override', '/overrides/new')

    # Auto-completion search
    config.add_route('latest_candidates', '/latest_candidates')
    config.add_route('latest_builds', '/latest_builds')
    config.add_route('get_sidetags', '/get_sidetags')
    config.add_route('latest_builds_in_tag', '/latest_builds_in_tag')

    # Include the auth system (after loading the models)
    config.include("bodhi.server.auth")

    config.add_route('api_version', '/api_version')
    config.add_route('liveness', '/healthz/live')
    config.add_route('readyness', '/healthz/ready')

    # service endpoints
    config.add_route('get_critpath_components', '/get_critpath_components')

    # Legacy: Redirect the previously self-hosted documentation
    # https://docs.pylonsproject.org/projects/pyramid/en/latest/narr/hybrid.html#using-subpath-in-a-route-pattern
    config.add_route("docs", "/docs/*subpath")

    config.scan('bodhi.server.views')
    config.scan('bodhi.server.services')
    config.scan('bodhi.server.webapp')

    # Though importing in the middle of this function is the darkest of evils, we cannot do it any
    # other way without a backwards-incompatible change. See
    # https://github.com/fedora-infra/bodhi/issues/2294
    from bodhi.server import models
    from bodhi.server.views import generic

    # Let's put a cache on the home page stats, but only if it isn't already cached. The cache adds
    # an invalidate attribute to the method, so that's how we can tell. The server would not
    # encounter this function already having a cache in normal operation, but the unit tests do run
    # this function many times so we don't want them to cause it to cache a cache of the cache of
    # the cache…
    if not hasattr(generic._generate_home_page_stats, 'invalidate'):
        generic._generate_home_page_stats = get_cacheregion(None).cache_on_arguments()(
            generic._generate_home_page_stats)

    if bodhi_config['warm_cache_on_start']:
        log.info('Warming up caches…')

        # Let's warm up the Release.all_releases and Release_get_tags caches.
        # We can just call the function - we don't need to capture the return value.
        models.Release.all_releases()
        models.Release.get_tags()

        # Let's warm up the home page cache by calling _generate_home_page_stats(). We can ignore
        # the return value.
        generic._generate_home_page_stats()

    # Let's close out the db session we used to warm the caches.
    Session.remove()

    log.info('Bodhi ready and at your service!')
    app = config.make_wsgi_app()
    return app
