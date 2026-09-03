import requests

class BundestagVoteCrawler:
    """ Client for access the bundestag API"""
    def __init__(self, base_url="https://www.bundestag.de"):
        self.base_url = base_url
        self.vote_list_url = f"{base_url}/parlament/plenum/abstimmung/liste"
        self.session = requests.Session()





    def get_members(self):
        """ Get all members of the bundestag"""
        url = "https://www.bundestag.de/service/opendata/abgeordnete"
        response = requests.get(url)
        return response.json()
