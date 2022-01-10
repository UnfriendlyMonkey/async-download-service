from aiohttp import web
import aiofiles
import asyncio
import datetime
import time


INTERVAL_SECS = 1
DIR = '/home/andrey/5_My_projects/Dvmn/photozip/'
SERVER_DIR = f'{DIR}async-download-service/test_photos/'
TEST_DIR = f'{DIR}Dvmn/'


async def uptime_handler(request):
    response = web.StreamResponse()

    # Большинство браузеров не отрисовывают частично загруженный контент, только если это не HTML.
    # Поэтому отправляем клиенту именно HTML, указываем это в Content-Type.
    response.headers['Content-Type'] = 'text/html'

    # Отправляет клиенту HTTP заголовки
    await response.prepare(request)

    while True:
        formatted_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f'{formatted_date}<br>'  # <br> — HTML тег переноса строки

        # Отправляет клиенту очередную порцию ответа
        await response.write(message.encode('utf-8'))

        await asyncio.sleep(INTERVAL_SECS)


async def archivate(request):
    archive_hash = request.match_info.get('archive_hash', "7kna")
    print(f'ARCH_HASH: {archive_hash}')
    response = web.StreamResponse()
    response.headers['Content-Type'] = 'application/octet-stream'
    response.headers['Content-Disposition'] = f'attachment; filename="{archive_hash}.zip"'

    await response.prepare(request)

    process = await asyncio.create_subprocess_shell(
        f'zip -rj - {SERVER_DIR}{archive_hash}',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    file = open(f'{TEST_DIR}{archive_hash}.zip', 'w+b')
    file.seek(0)
    iteration = 0
    while True:
        iteration += 1
        stdout = await process.stdout.read(25000)
        if process.stdout.at_eof():
            break
        print(f'ITERATION: {iteration}, BITES: {stdout}')
        file.write(stdout)
        await response.write(stdout)

    await response.write_eof()
    file.close()
    return response


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')


if __name__ == '__main__':
    app = web.Application()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', archivate),
        web.get('/uptime/', uptime_handler),
    ])
    web.run_app(app)
