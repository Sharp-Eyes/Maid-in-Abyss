all = (
    "GenshinAPIError",
    "CookieError",
    "CodeRedeemError",
    "validate_API_response",
    "AlreadySigned",
    "FirstSign",
    "UnintelligibleResponseError"
)


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
            self.message = f"An unexpected error occurred: [retcode {self.retcode}]_{self.message}_"

    def __str__(self):
        return self.message


class CookieError(GenshinAPIError):
    """Authorization cookies were either incorrectly provided, or not provided at all."""


class TooManyLogins(GenshinAPIError):
    """Attempted to login to the API in too quick succession."""


class CodeRedemptionError(GenshinAPIError):
    """Error in code redemption; has multiple causes."""


class IncorrectCodeError(CodeRedemptionError):
    """The code entered was incorrect."""


class AlreadyClaimed(CodeRedemptionError):
    """The code entered had already been claimed by the user."""


def validate_API_response(response: dict):
    """Raises an error corresponding to the provided response."""

    error = {
        -100: CookieError(
            "{0.mention}, your authorization cookies appear to be incorrect. "
            "Please check your cookies and re-enter them through `/gwiki auth`."
        ),
        10001: CookieError(
            "{0.mention}, your authorization cookies appear to be incorrect. "
            "Please check your cookies and re-enter them through `/gwiki auth`."
        ),
        -1004: TooManyLogins(
            "{0.mention}, you are trying to login too frequently. "
            "Please wait a moment and try again."
        ),
        -2003: IncorrectCodeError(
            "{0.mention}, the redeem code you entered appears to be incorrect. "
            "Please check the redeem code and try again."
        ),
        -2017: AlreadyClaimed(
            "{0.mention}, you appear to have already redeemed this code. "
            "Please check the redeem code and try again."
        ),
        -2001: CodeRedemptionError(
            "{0.mention}, the redeem code you entered appears to have expired."
        ),
        -2021: CodeRedemptionError(
            "{0.mention}, account {1} appears to have not yet reached AR10 yet. "
            "Regrettably, accounts under AR10 cannot claim redemption codes."
        ),
        -1073: CodeRedemptionError(
            "{0.mention}, the account you provided appears to not have any game "
            "accounts bound to it. Therefore, I am unable to claim your rewards. "
            "Please check whether you entered the correct authorization cookies."
        ),
        -1071: CookieError(
            "{0.mention}, you appear not to have set your `ACCOUNT_ID` and "
            "`COOKIE_TOKEN` authorization cookies. Though these are optional for "
            "most API endpoints, unfortunately code redemption requires them to be set. "
            "Please enter the missing cookies using `/gwiki auth set` if you wish to be "
            "able to use redeem codes."
        )
    }.get(response["retcode"], GenshinAPIError())

    error.set_response(response)
    raise error

# Errors not based on retcodes


class AlreadySigned(GenshinAPIError):
    """Attempted to claim check-in rewards when this had already been done today."""


class FirstSign(GenshinAPIError):
    """Attempted to claim check-in rewards without first having claimed once manually."""

# class AccountNotFound(GenshinAPIError):
#     """Passed an invalid UID """


class UnintelligibleResponseError(GenshinAPIError):
    """API response cannot be converted to json or is otherwise in some unexpected format."""

    def __init__(self, response: str):
        self.message = response
