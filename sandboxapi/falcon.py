from __future__ import print_function

import sys
import json

import sandboxapi

class FalconAPI(sandboxapi.SandboxAPI):
    """Falcon Sandbox API wrapper"""

    def __init__(self, key, secret, url=None, env=100):
        """Initialize the interface to Falcon Sandbox API with key and secret"""
        sandboxapi.SandboxAPI.__init__(self)

        self.api_url = url or 'https://www.reverse.it'
        self.key = key
        self.secret = secret
        self.env_id = str(env)

    def _request(self, uri, method='GET', params=None, files=None, headers=None):
        """Override the parent _request method.

        We have to do this here because FireEye requires some extra
        authentication steps.
        """
        if params:
            params['apikey'] = self.key
            params['secret'] = self.secret
            params['environmentId'] = self.env_id
        else:
            params = {
                'apikey': self.key,
                'secret': self.secret,
                'environmentId': self.env_id,
            }

        if headers:
            headers['User-Agent'] = 'Falcon Sandbox Lib'
        else:
            headers = {
                'User-Agent': 'Falcon Sandbox Lib',
            }

        return sandboxapi.SandboxAPI._request(self, uri, method, params, files, headers)


    def analyze(self, handle, filename):
        """Submit a file for analysis.

        @type  handle:   File handle
        @param handle:   Handle to file to upload for analysis.
        @type  filename: str
        @param filename: File name.

        @rtype:  str
        @return: File hash as a string
        """
        # multipart post files.
        files = {"file" : (filename, handle)}

        # ensure the handle is at offset 0.
        handle.seek(0)

        response = self._request("/api/submit", method='POST', files=files)

        try:
            if response.status_code == 200 and int(response.json()['response_code']) == 0:
                # good response
                return response.json()['response']['sha256']
            else:
                raise sandboxapi.SandboxError("api error in analyze: {r}".format(r=response.content))
        except (ValueError, KeyError) as e:
            raise sandboxapi.SandboxError("error in analyze: {e}".format(e=e))

    def check(self, item_id):
        """Check if an analysis is complete.

        @type  item_id: str
        @param item_id: File hash to check.

        @rtype:  bool
        @return: Boolean indicating if a report is done or not.
        """
        response = self._request("/api/state/{hash}".format(hash=item_id))

        if response.status_code == 404:
            # probably an unknown task id
            return False

        try:
            content = json.loads(response.content.decode('utf-8'))
            status = content['response']['state']
            if status == 'SUCCESS' or status == 'ERROR':
                return True

        except ValueError as e:
            raise sandboxapi.SandboxError(e)

        return False

    def is_available(self):
        """Determine if the Falcon API server is alive.

        @rtype:  bool
        @return: True if service is available, False otherwise.
        """
        # if the availability flag is raised, return True immediately.
        # NOTE: subsequent API failures will lower this flag. we do this here
        # to ensure we don't keep hitting Falcon with requests while
        # availability is there.
        if self.server_available:
            return True

        # otherwise, we have to check with the cloud.
        else:

            try:
                response = self._request("/api/quota")

                # we've got falcon.
                if response.status_code == 200:
                    self.server_available = True
                    return True

            except Exception:
                pass

        self.server_available = False
        return False

    def queue_size(self):
        """Determine Falcon sandbox queue length

        @rtype:  str
        @return: Details on the queue size.
        """
        response = self._request("/system/queuesize")

        return response.content

    def report(self, item_id, report_format="json"):
        """Retrieves the specified report for the analyzed item, referenced by item_id.

        Available formats include: json, html.

        @type  item_id:     str
        @param item_id:     File ID number
        @type  report_format: str
        @param report_format: Return format

        @rtype:  dict
        @return: Dictionary representing the JSON parsed data or raw, for other
                 formats / JSON parsing failure.
        """
        report_format = report_format.lower()

        response = self._request("/api/scan/{file_hash}".format(file_hash=item_id),
                                 params={'type':report_format})

        # if response is JSON, return it as an object
        if report_format == "json":
            try:
                return json.loads(response.content.decode('utf-8'))
            except ValueError:
                pass

        # otherwise, return the raw content.
        return response.content


if __name__ == "__main__":

    def usage():
        msg = "%s: <key> <secret> <analyze <fh> | available | queue | report <id>>"
        print(msg % sys.argv[0])
        sys.exit(1)

    if len(sys.argv) == 4:
        cmd = sys.argv.pop().lower()
        secret = sys.argv.pop().lower()
        key = sys.argv.pop().lower()
        arg = None

    elif len(sys.argv) == 5:
        arg = sys.argv.pop()
        cmd = sys.argv.pop().lower()
        secret = sys.argv.pop().lower()
        key = sys.argv.pop().lower()

    else:
        usage()

    # instantiate Falcon Sandbox API interface.
    falcon = FalconAPI(key, secret)

    # process command line arguments.
    if "analyze" in cmd:
        if arg is None:
            usage()
        else:
            with open(arg, "rb") as handle:
                print(falcon.analyze(handle, arg))

    elif "available" in cmd:
        print(falcon.is_available())

    elif "queue" in cmd:
        print(falcon.queue_size())

    elif "report" in cmd:
        if arg is None:
            usage()
        else:
            print(falcon.report(arg))

    else:
        usage()
