import aiohttp
import argparse
import asyncio
from colorama import Fore
from getpass import getpass
import requests
import requests.utils as request_utils

BASE_URL = 'https://api.github.com'


EXTENSION_MAPPING = {
    'c':    'C',
    'cpp':  'C++',
    'go':   'Go',
    'hs':   'Haskell',
    'html': 'HTML',
    'java': 'Java',
    'js':   'Javascript',
    'jsx':  'Javascript',
    'php':  'PHP',
    'py':   'Python',
    'rb':   'Ruby',
    'rust': 'Rust',
    'sql':  'SQL',
    'sh':   'Shell',
}


async def main():
    (session_user, passw, auth_code) = get_creds()
    parser = argparse.ArgumentParser(
        description='Find the user github contributions by language',
    )
    parser.add_argument('-u', '--user', type=str, nargs='?', default=session_user)
    user = parser.parse_args().user
    auth = aiohttp.BasicAuth(session_user, passw)
    headers = {'X-GitHub-OTP': auth_code}
    async with aiohttp.ClientSession(auth=auth, headers=headers) as session:
        stats = await get_stats(session, user)
    for language, stat in stats.items():
        added = stat.added
        deleted = stat.deleted
        total = added + deleted
        net = added - deleted
        if net > 0:
            net_color = Fore.GREEN
        elif net < 0:
            net_color = Fore.RED
        else:
            net_color = Fore.RESET
        print()
        print(language)
        print()
        print(Fore.GREEN + f'    Added:   {added}')
        print(Fore.RED + f'    Deleted: {deleted}')
        print(Fore.RESET + f'    Total:   {total}')
        print(net_color + f'    Net:     {net}')
        print(Fore.RESET)


async def get_stats(session, user):
    async with session.get(f'{BASE_URL}/users/{user}/events') as response:
        response.raise_for_status()
        events = await response.json()
        iterator = EventIterator(session, response.headers, events)
    event_handles = []
    async for event in iterator:
        event_handles.append(handle_event(session, user, event))
    event_commits = await asyncio.gather(*event_handles)
    stats = {lang: StatTracker() for lang in EXTENSION_MAPPING.values()}
    for commit_data in flatten(event_commits):
        language = commit_data.get_language()
        if language:
            stats[language].update(commit_data)
    return {l: s for l, s in stats.items() if s.added or s.deleted}


async def handle_event(session, user, event):
    if event['type'] != 'PushEvent' or event['actor']['login'] != user:
        return []
    repo = event['repo']['name']
    commit_data_fetches = []
    for commit in event['payload']['commits']:
        if commit['author']['name'] != user:
            continue
        commit_data_fetches.append(
            fetch_commit_data(
                session,
                repo,
                commit['sha'],
            ),
        )
    commit_datas = await asyncio.gather(*commit_data_fetches)
    return flatten(commit_datas)


async def fetch_commit_data(session, repo, sha):
    async with session.get(f'{BASE_URL}/repos/{repo}/commits/{sha}') as response:
        response_json = await response.json()
        files = response_json.get('files', [])
        return [FileCommitData(file_data) for file_data in files]


def get_creds():
    user = input('user:')
    password = getpass('password:')
    auth_code = input('code (if using 2 fac):')
    return (user, password, auth_code)


def flatten(ls):
    """Flatten a list of lists"""
    return [item for l in ls for item in l]



class StatTracker:

    def __init__(self):
        self.added = 0
        self.deleted = 0

    def update(self, file_commit_data):
        self.added += file_commit_data.additions
        self.deleted += file_commit_data.deletions


class FileCommitData:

    def __init__(self, file_data):
        self.file_name = file_data['filename']
        self.additions = file_data['additions']
        self.deletions = file_data['deletions']

    def get_language(self):
        return EXTENSION_MAPPING.get(self.file_name.split('.')[-1])


class EventIterator:

    def __init__(self, session, headers, events):
        self.session = session
        self.headers = headers
        self.events = events

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.events:
            return self.events.pop(0)
        await self.refresh()
        return await self.__anext__()

    async def refresh(self):
        header_links = self.headers.get('link')
        if not header_links:
            raise StopAsyncIteration
        links = request_utils.parse_header_links(header_links)
        next_url = None
        for link in links:
            if link.get('rel') == 'next':
                next_url = link['url']
                break
        else:
            raise StopAsyncIteration

        async with self.session.get(next_url) as response:
            self.headers = response.headers
            self.events = await response.json()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
