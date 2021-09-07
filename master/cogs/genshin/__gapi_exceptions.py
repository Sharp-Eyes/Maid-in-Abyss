class GenshinAPIError(Exception):
    """Base exception for all errors to do with the Genshin API."""

    retcode: int = 0
    response_message: str = 0

    def __init__(self, message: str = ""):
        self.message = message

    def set_response(self, response: dict):
        self.retcode = response["retcode"]
        self.response_message = response["message"]
        if not self.message:
            self.message = f"An unexpected error occurred: [retcode {self.retcode}] _{self.message}_"

    def __str__(self):
        return self.message


class CookieError(GenshinAPIError):
    """Authorization cookies were either incorrectly provided, or not provided at all."""

class CodeRedeemError(GenshinAPIError):
    """An error occurred in trying to claim rewards for a redemption code."""

class TooManyLogins(GenshinAPIError):
    """Attempted to login to the API in too quick succession."""



class UnintelligibleResponseError(GenshinAPIError):
    """API response cannot be converted to json or is otherwise in some unexpected format."""
    
    def __init__(self, response: str):
        self.message = response





def validate_API_response(response: dict):
    """Raises an error corresponding to the provided response."""

    error = {
        -100:  CookieError("{0.mention}, your authorization cookies appear to be incorrect. Please check your cookies and re-enter them through `/gwiki auth`."),
        10001: CookieError("{0.mention}, your authorization cookies appear to be incorrect. Please check your cookies and re-enter them through `/gwiki auth`."),
        -1004: TooManyLogins("{0.mention}, you are trying to login too frequently. Please wait a moment and try again.")
    }.get(response["retcode"], GenshinAPIError())
    
    error.set_response(response)
    raise error