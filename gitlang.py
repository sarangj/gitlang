import requests

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


def get_stats(session, user=None):
    user = user or session.auth[0]
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
    password = input('password:')
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
        links = self.headers.get('Link')
        if not links:
            raise StopIteration()

        next_link = None
        for link in links.split(','):
            [l, rel] = link.split(';')
            if rel == 'next':
                next_link = l
                break

        if not next_link:
            raise StopIteration()

        response = session.get(next_link)
        self.headers = response.headers
        self.events = response.json()


session = authenticate()
stats = get_stats(session, 'sarangj')
for language, stat in stats.items():
    added = stat.added
    deleted = stat.deleted
    total = added + deleted
    net = added - deleted
    print()
    print(language)
    print()
    print(f'    Added:   {added}')
    print(f'    Deleted: {deleted}')
    print(f'    Total:   {total}')
    print(f'    Net:     {net}')
