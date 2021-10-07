from .api import *
from .user import *
from .check_in import *
from .cdkey import *

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/58.0.3029.110 Safari/537.36"
)
HEADERS = {
    # required headers
    "x-rpc-app_version": "1.5.0",  # overseas api uses 1.x.x, chinese api uses 2.x.x
    "x-rpc-client_type": "4",
    "x-rpc-language": "en-us",
    # authentication headers
    "ds": "",
    # recommended headers
    "user-agent": USER_AGENT
}
