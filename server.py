from os import path, getenv
from sys import exit
from aiohttp import web
import aiofiles
import asyncio
import logging
import argparse
from functools import partial


INTERVAL_SECS = 1
LOG_FORMAT = '%(filename)s[LINE:%(lineno)d]# %(levelname)-8s [%(asctime)s]  %(message)s'


async def archivate(request, archive_path, throttling=False):
    archive_hash = request.match_info['archive_hash']
    path_exists = path.exists(f'{archive_path}{archive_hash}')
    if not path_exists:
        logging.error("Path {archive_path}{archive_hash} doesn't exist")
        raise web.HTTPNotFound(
            text="Sorry. Archive you are asking for doesn't exist"
        )
    logging.debug(f'Path {archive_path}{archive_hash} exists')
    response = web.StreamResponse()
    response.headers['Content-Type'] = 'application/octet-stream'
    content_disposition = f'attachment; filename="{archive_hash}.zip"'
    response.headers['Content-Disposition'] = content_disposition

    # Отправляет клиенту HTTP заголовки
    await response.prepare(request)

    process = await asyncio.create_subprocess_exec(
        'zip',
        '-r',
        '-',
        f'{archive_path}{archive_hash}',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    iteration = 0
    try:
        while True:
            iteration += 1
            stdout = await process.stdout.read(250000)
            if process.stdout.at_eof():
                logging.debug("EOF")
                break
            logging.debug(
                f'Sending archive chunk ... iteration:\
                {iteration}, bites: {len(stdout)}'
            )
            # Отправляет клиенту очередную порцию ответа
            await response.write(stdout)
            # Пауза для проверки разрыва соединения по инициативе клиента
            if throttling:
                await asyncio.sleep(INTERVAL_SECS)

    except (asyncio.CancelledError, SystemExit):
        logging.debug('Download was interrupted')
        # отпускаем перехваченный CancelledError
        raise

    finally:
        # закрывать соединение,
        # останавливать дочерний процесс даже в случае ошибки
        await response.write_eof()
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        await process.communicate()

    return response


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Web-server for downloading photoarchives'
    )
    parser.add_argument(
        'path',
        nargs='?',
        help='absolute path to the directory with photoarchives'
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
    throttling = args.throttling

    module_path = path.dirname(path.abspath(__file__))
    if args.path:
        archive_path = args.path
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
    handle_archivation = partial(
        archivate,
        archive_path=archive_path,
        throttling=throttling
    )
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', handle_archivation),
    ])
    web.run_app(app)


if __name__ == '__main__':
    main()
