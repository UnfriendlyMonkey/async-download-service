from os import path, getenv
from sys import exit
from aiohttp import web
import aiofiles
import asyncio
import datetime
import logging
import argparse


INTERVAL_SECS = 1
LOG_FORMAT = u'%(filename)s[LINE:%(lineno)d]# %(levelname)-8s [%(asctime)s]  %(message)s'


async def uptime_handler(request):
    response = web.StreamResponse()

    # Большинство браузеров не отрисовывают частично загруженный контент,
    # только если это не HTML.
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
    logging.debug(f'ARCH_HASH: {archive_hash}')

    path_exists = path.exists(f'{archive_path}{archive_hash}')
    if not path_exists:
        logging.error("Path doesn't exist")
        raise web.HTTPNotFound(
            text="Sorry. Archive you are asking for doesn't exist")
    logging.debug(f'Path exists: {path_exists}')
    response = web.StreamResponse()
    response.headers['Content-Type'] = 'application/octet-stream'
    content_disposition = f'attachment; filename="{archive_hash}.zip"'
    response.headers['Content-Disposition'] = content_disposition

    # Отправляет клиенту HTTP заголовки
    await response.prepare(request)

    process = await asyncio.create_subprocess_shell(
        f'exec zip -rj - {archive_path}{archive_hash}',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    file = open(f'{control_path}{archive_hash}.zip', 'w+b')
    file.seek(0)
    iteration = 0

    try:
        while True:
            iteration += 1
            stdout = await process.stdout.read(250000)
            if process.stdout.at_eof():
                break
            logging.debug(
                f'Sending archive chunk ... iteration:\
                {iteration}, bites: {len(stdout)}')
            file.write(stdout)
            # Отправляет клиенту очередную порцию ответа
            await response.write(stdout)
            # Пауза для проверки разрыва соединения по инициативе клиента
            if is_throttling_on:
                await asyncio.sleep(INTERVAL_SECS)

    except (asyncio.CancelledError, SystemExit):
        logging.debug('Download was interrupted')
        # отпускаем перехваченный CancelledError
        raise

    finally:
        # закрывать файл и соединение,
        # останавливать дочерний процесс даже в случае ошибки
        await response.write_eof()
        file.close()
        process.terminate()
        _ = await process.communicate()

    return response


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')


def parse_arguments():

    parser = argparse.ArgumentParser(
            description='Web-server for downloading photoarchives')
    parser.add_argument(
            'path',
            nargs='?',
            help='path to the directory with photoarchives'
            )
    parser.add_argument(
            '-l',
            '--logging',
            action='store_true',
            help='turn on detailed logging'
            )
    parser.add_argument(
            '-t',
            '--throttling',
            action='store_true',
            help='turn on pause between packages to emulate slow connection'
            )
    args = parser.parse_args()

    return args


def main():
    args = parse_arguments()

    global is_throttling_on
    is_throttling_on = args.throttling

    global archive_path
    global control_path
    module_path = path.dirname(path.abspath(__file__))
    control_path = f'{module_path}/control_files/'
    if args.path:
        if args.path.startswith('/'):
            archive_path = args.path
        else:
            archive_path = f'{getenv("PWD")}/{args.path}'
        if not archive_path.endswith('/'):
            archive_path += '/'
    else:
        archive_path = f'{module_path}/test_photos/'

    if not path.exists(archive_path):
        logging.error("Provided path doesn't exist")
        exit(1)

    log_level = logging.DEBUG if args.logging else logging.WARNING
    logging.basicConfig(format=LOG_FORMAT, level=log_level)
    logging.debug("Log level DEBUG is on")

    app = web.Application()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', archivate),
        web.get('/uptime/', uptime_handler),
    ])
    web.run_app(app)


if __name__ == '__main__':
    main()
