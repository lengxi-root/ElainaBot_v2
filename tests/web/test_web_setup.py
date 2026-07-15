from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from web.setup import _make_spa_handler, _missing_dist_assets, _select_dist_dir


def _write_dist(dist_dir, *, referenced=(), present=()):
    assets_dir = dist_dir / 'assets'
    assets_dir.mkdir(parents=True)
    (dist_dir / 'index.html').write_text(
        '<script type="module" src="/web/assets/index.js"></script>',
        encoding='utf-8',
    )
    refs = ','.join(f'"assets/{name}"' for name in referenced)
    (assets_dir / 'index.js').write_text(f'const deps=[{refs}]', encoding='utf-8')
    for name in present:
        (assets_dir / name).write_text('export default true', encoding='utf-8')


def test_select_dist_prefers_complete_packaged_build(tmp_path):
    project_dir = tmp_path / 'project'
    packaged = project_dir / 'web' / 'dist'
    alternate = project_dir / 'web-vue' / 'dist'
    _write_dist(packaged, referenced=('Update.js',), present=('Update.js',))
    _write_dist(alternate, referenced=('Old.js',), present=('Old.js',))

    selected = _select_dist_dir(str(project_dir), str(project_dir / 'web'))

    assert selected == str(packaged)


def test_select_dist_skips_incomplete_packaged_build(tmp_path):
    project_dir = tmp_path / 'project'
    packaged = project_dir / 'web' / 'dist'
    alternate = project_dir / 'web-vue' / 'dist'
    _write_dist(packaged, referenced=('Update.js',))
    _write_dist(alternate, referenced=('Update.js',), present=('Update.js',))

    assert _missing_dist_assets(str(packaged)) == ['assets/Update.js']
    assert _select_dist_dir(str(project_dir), str(project_dir / 'web')) == str(alternate)


async def test_spa_handler_distinguishes_assets_from_routes(tmp_path):
    dist_dir = tmp_path / 'dist'
    _write_dist(dist_dir, referenced=('Update.js',), present=('Update.js',))
    app = web.Application()
    app.router.add_get('/web/{path:.*}', _make_spa_handler(str(dist_dir)))
    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)
    await client.start_server()

    try:
        module_response = await client.get('/web/assets/Update.js')
        assert module_response.status == 200
        assert module_response.headers['Content-Type'] == 'application/javascript'

        missing_response = await client.get('/web/assets/Missing.js')
        assert missing_response.status == 404
        assert missing_response.headers['Content-Type'].startswith('text/plain')
        assert await missing_response.text() == 'Not Found'

        route_response = await client.get('/web/openapi')
        assert route_response.status == 200
        assert route_response.headers['Content-Type'] == 'text/html'
        assert 'assets/index.js' in await route_response.text()
    finally:
        await client.close()
        await server.close()
