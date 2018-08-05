import argparse
from colorama import Fore
from getpass import getpass
import requests
import requests.utils as request_utils

BASE_URL = 'https://api.github.com'


EXTENSION_MAPPING = {
    'c':    'C',
    'cpp':  'C++',
    'hs':   'Haskell',
    'java': 'Java',
    'js':   'Javascript',
    'jsx':  'Javascript',
    'py':   'Python',
    'rust': 'Rust',
    'sql':  'SQL',
}


def main():
    session = authenticate()
    (session_user, _) = session.auth
    parser = argparse.ArgumentParser(
        description='Find the user github contributions by language',
    )
    parser.add_argument('-u', '--user', type=str, nargs='?', default=session_user)
    user = parser.parse_args().user
    stats = get_stats(session, user)
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


def get_stats(session, user):
    stats = {lang: StatTracker() for lang in EXTENSION_MAPPING.values()}
    response = session.get(f'{BASE_URL}/users/{user}/events')
    iterator = EventIterator(session, response)
    for event in iterator:
        if event['type'] != 'PushEvent' or event['actor']['login'] != user:
            continue
        repo = event['repo']['name']
        for commit in event['payload']['commits']:
            if commit['author']['name'] != user:
                continue
            sha = commit['sha']
            commit_response = session.get(f'{BASE_URL}/repos/{repo}/commits/{sha}')
            for file_data in commit_response.json().get('files', []):
                commit_data = FileCommitData(file_data)
                language = commit_data.get_language()
                if language:
                    stats[language].update(commit_data)
    return {l: s for l, s in stats.items() if s.added or s.deleted}


def authenticate():
    user = input('user:')
    password = getpass('password:')
    auth_code = input('code (if using 2 fac):')
    session = requests.Session()
    session.auth = (user, password)
    if auth_code:
        session.headers.update({'X-GitHub-OTP': auth_code})
    return session


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

    def __init__(self, session, response):
        self.session = session
        self.headers = response.headers
        response.raise_for_status()
        self.events = response.json()

    def __iter__(self):
        return self

    def __next__(self):
        if self.events:
            return self.events.pop(0)
        self.refresh()
        return self.__next__()

    def refresh(self):
        header_links = self.headers.get('link')
        if not header_links:
            raise StopIteration
        links = request_utils.parse_header_links(header_links)
        next_url = None
        for link in links:
            if link.get('rel') == 'next':
                next_url = link['url']
                break
        else:
            raise StopIteration

        response = self.session.get(next_url)
        self.headers = response.headers
        self.events = response.json()

if __name__ == '__main__':
    main()
