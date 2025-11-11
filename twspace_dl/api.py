from __future__ import annotations

import json
import logging
import re
import urllib
from typing import Any, NoReturn

import requests
from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import ConnectionError, HTTPError, Timeout, TooManyRedirects, RetryError
from json import JSONDecodeError

from .cookies import validate_cookies

"""Twitter unofficial API authorization header."""
TWITTER_AUTHORIZATION = "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

"""Retry parameters for making all requests."""
RETRY = Retry(
    total=5,
    connect=3,
    read=2,
    redirect=3,
    backoff_factor=0.2,
    status_forcelist=(500, 502, 503, 504),
)

"""Default connection timeout for making all requests."""
TIMEOUT = 20


class HTTPClient:
    """The HTTP client for making requests."""

    def __init__(self) -> None:
        """Initialize the client with a requests session and mount the default retry adapter."""
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=RETRY))

    def get(
            self,
            url: str,
            params: dict[str, str] = {},
            headers: dict[str, str] = {},
            cookies: dict[str, str] = {},
            timeout: int = TIMEOUT
    ) -> requests.Response:
        """Send HTTP GET requests to the specified URL.

        - url: The URL to send the GET request to.
        - params: Query parameters of the request.
        - headers: HTTP headers of the request.
        - cookies: HTTP cookies of the request.
        - timeout: The connection timeout of the request, default to the static value specified above.

        - return: The response of the request.

        - raise RuntimeError: Raised when the request was not successful (max retries, timeouts, and
          4xx and 5xx HTTP status codes).
        """
        try:
            response = self.session.get(
                url, params=params, headers=headers, cookies=cookies, timeout=timeout
            )
            response.raise_for_status()
            return response
        except RetryError as e:
            logging.error(
                f"Max retries exceeded with URL: {e.request.url}, reason: {e.args[0].reason}"
            )
            raise RuntimeError("API request failed after max retries") from e
        except ConnectionError as e:
            logging.error(
                f"Connection error occurred with URL: {e.request.url}, reason: {e.args[0].reason}"
            )
            raise RuntimeError("API request failed with connection error") from e
        except HTTPError as e:
            if e.response.status_code == requests.codes.TOO_MANY_REQUESTS:
                logging.error(f"API rate limit exceeded with URL: {url}")
                raise
            logging.error(
                f"HTTP error occurred with URL: {e.request.url}, status code: {e.response.status_code}"
            )
            raise RuntimeError("API request failed with HTTP error") from e


class APIClient:
    """Base API client."""

    """Base URL of the API."""
    _API_URL = "https://x.com/i/api"

    def __init__(self, client: HTTPClient, path: str, cookies: dict[str, str]) -> None:
        """Initialize the API client.

        - client: The `HTTPClient` instance to send requests.
        - path: The path to add to the base URL of the API.
        - cookies: The cookies used for making all requests to the API.
        """
        validate_cookies(cookies)
        self.client = client
        self.base_url = self.join_url(self._API_URL, path)
        self.cookies = cookies
        self.headers = {
            "authorization": TWITTER_AUTHORIZATION,
            "x-csrf-token": cookies["ct0"],
        }

    def join_url(self, *paths: str) -> str:
        """Join all the specified paths to a single URL.

        - paths: The components of the URL to be joined.
        """
        return "/".join(path.strip("/") for path in paths)

    def get(self, path: str, params: dict[str, str] = {}) -> Any:
        """Send HTTP GET requests to the specified path of the API with the specified query parameters.

        - path: The path to send the API request to.
        - params: Query parameters of the request.

        - return: The object decoded from the JSON string returned from the API.

        - raise RuntimeError: If the response from the API cannot be decoded as a JSON string.
        """
        try:
            response = self.client.get(
                self.join_url(self.base_url, path),
                params=params,
                headers=self.headers,
                cookies=self.cookies,
            )
            return response.json()
        except JSONDecodeError:
            logging.error(
                f"Cannot decode response from URL: {response.url}, status code: {response.status_code}"
            )
            logging.debug(f"Response text: {response.text!r}")
            raise RuntimeError("API response cannot be decoded as JSON")


class GraphQLAPI(APIClient):
    """Twitter GraphQL API client."""

    def __init__(self, client: HTTPClient, path: str, cookies: dict[str, str]) -> None:
        """Initialize the Twitter GraphQL API client.

        - client: The `HTTPClient` instance to send requests.
        - path: The path to add to the base URL of the API.
        - cookies: The cookies used for making all requests to the API.
        """
        super().__init__(client, path, cookies)

    def _dump_json(self, obj: Any) -> str:
        """Serialize the object to a compact JSON string.

        The object will be returned directly if it is a string.

        - obj: The object to be serialized to JSON.

        - return: A compact JSON string representing the specified object.
        """
        if isinstance(obj, str):
            return obj
        return json.dumps(obj, indent=None, separators=(",", ":"))

    def get(
            self,
            query_id: str,
            operation_name: str,
            variables: dict[str, str] | str,
            features: dict[str, str] | str | None = None,
            field_toggles: dict[str, str] | str | None = None
    ) -> Any:
        """Send HTTP GET requests to the Twitter GraphQL API.

        - query_id: The query ID of the GraphQL API endpoint.
        - operation_name: The name of the operation to be executed.
        - variables: Query variables of the GraphQL query.
        - features: Feature switches of the GraphQL query.

        - return: The returned object of the query.
        """
        params = {"variables": self._dump_json(variables)}
        if features:
            params["features"] = self._dump_json(features)
        if field_toggles:
            params["fieldToggles"] = self._dump_json(field_toggles)
        return super().get(self.join_url(query_id, operation_name), params)

    def audio_space_by_id_old(self, space_id: str) -> dict:
        """Query Twitter Space details by its ID.

        - space_id: The ID of the Twitter Space.

        - return: The details of the queried Twitter Space.
        """
        query_id = "xVEzTKg_mLTHubK5ayL0HA"
        operation_name = "AudioSpaceById"
        variables = {
            "id": space_id,
            "isMetatagsQuery": True,
            "withReplays": True,
            "withListeners": True,
        }
        # "features" is copied as-is from real requests
        features = '{"spaces_2022_h2_clipping":true,"spaces_2022_h2_spaces_communities":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"tweetypie_unmention_optimization_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":false,"tweet_awards_web_tipping_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_media_download_video_enabled":false,"responsive_web_enhance_cards_enabled":false}'
        return self.get(query_id, operation_name, variables, features)

    def audio_space_by_id(self, space_id: str) -> dict:
        url = "https://x.com/i/api/graphql/pCUWlI5FNL7ROBjmBsH3Zw/AudioSpaceById"
        params = {
            "variables": '{"id":"space_id","isMetatagsQuery":true,"withReplays":true,"withListeners":true}',
            "features": '{"spaces_2022_h2_spaces_communities":true,"spaces_2022_h2_clipping":true,"creator_subscriptions_tweet_preview_api_enabled":true,"payments_enabled":false,"profile_label_improvements_pcf_label_in_post_enabled":true,"responsive_web_profile_redirect_enabled":false,"rweb_tipjar_consumption_enabled":true,"verified_phone_label_enabled":false,"premium_content_api_read_enabled":false,"communities_web_enable_tweet_community_results_fetch":true,"c9s_tweet_anatomy_moderator_badge_enabled":true,"responsive_web_grok_analyze_button_fetch_trends_enabled":false,"responsive_web_grok_analyze_post_followups_enabled":true,"responsive_web_jetfuel_frame":true,"responsive_web_grok_share_attachment_enabled":true,"articles_preview_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":true,"tweet_awards_web_tipping_enabled":false,"responsive_web_grok_show_grok_translated_post":false,"responsive_web_grok_analysis_button_from_backend":true,"creator_subscriptions_quote_tweet_preview_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_grok_image_annotation_enabled":true,"responsive_web_grok_imagine_annotation_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_grok_community_note_auto_translation_is_enabled":false,"responsive_web_enhance_cards_enabled":false}'
        }
        params['variables'] = params['variables'].replace('space_id', space_id)

        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Authorization": TWITTER_AUTHORIZATION,
            "Content-Type": "application/json",
            "Referer": f"https://x.com/i/spaces/{space_id}",
            "Sec-CH-UA": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "X-Client-Transaction-Id": "tA5vYayNBAqFK3QWjvLzdAawt9ETc7zV/8lv41a5a85d84SqSVXYjeH8+ijVcHNQF+z5dLeA/fFb7O0u1P39ZXcynFuwtw",
            "X-Client-UUID": "3cf67b4d-737f-4e0e-b39b-b22939dcf33c",
            "X-Twitter-Active-User": "yes",
            "X-Twitter-Auth-Type": "OAuth2Session",
            "X-Twitter-Client-Language": "en"
        }

        cookies = self.cookies
        headers["X-CSRF-Token"] = cookies["ct0"]
        response = requests.get(url, headers=headers, params=params, cookies=cookies)

        return response.json()

    def user_by_screen_name(self, screen_name: str) -> dict:
        """Query Twitter user details by their screen name (@ handle).

        - screen_name: The screen name (@ handle) of the Twitter user.

        - return: The details of the queried Twitter user.
        """
        url = "https://x.com/i/api/graphql/ZHSN3WlvahPKVvUxVQbg1A/UserByScreenName"
        params = {
            "variables": '{"screen_name":"screen_name_placeholder","withGrokTranslatedBio":false}',
            "features": '{"hidden_profile_subscriptions_enabled":true,"payments_enabled":false,"profile_label_improvements_pcf_label_in_post_enabled":true,"responsive_web_profile_redirect_enabled":false,"rweb_tipjar_consumption_enabled":true,"verified_phone_label_enabled":false,"subscriptions_verification_info_is_identity_verified_enabled":true,"subscriptions_verification_info_verified_since_enabled":true,"highlights_tweets_tab_ui_enabled":true,"responsive_web_twitter_article_notes_tab_enabled":true,"subscriptions_feature_can_gift_premium":true,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_graphql_timeline_navigation_enabled":true}',
            "fieldToggles": '{"withAuxiliaryUserLabels":true}'
        }
        params['variables'] = params['variables'].replace('screen_name_placeholder', screen_name)

        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-CA,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
            "Authorization": TWITTER_AUTHORIZATION,
            "Content-Type": "application/json",
            "Referer": f"https://x.com/{screen_name}",
            "Sec-CH-UA": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Linux"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "X-Twitter-Active-User": "yes",
            "X-Twitter-Auth-Type": "OAuth2Session",
            "X-Twitter-Client-Language": "en"
        }

        cookies = self.cookies
        headers["X-CSRF-Token"] = cookies["ct0"]
        response = requests.get(url, headers=headers, params=params, cookies=cookies)

        return response.json()

    def profile_spotlights_query(self, screen_name: str) -> dict:
        """Backup API endpoint to query Twitter user details by their screen name (@ handle).

        The response data from this API contains less information of the user than the `user_by_screen_name`
        API, but still has the essential `rest_id` field. Therefore, it is used as a backup of the other API
        endpoint if the other one was rate limited.

        - screen_name: The screen name (@ handle) of the Twitter user.

        - return: The details of the queried Twitter user.
        """
        query_id = "9zwVLJ48lmVUk8u_Gh9DmA"
        operation_name = "ProfileSpotlightsQuery"
        variables = {"screen_name": screen_name}
        return self.get(query_id, operation_name, variables)

    def user_id(self, screen_name: str) -> str:
        """Retrieve the numeric user ID (`rest_id`) of the user with the specified screen name (@ handle).

        - screen_name: The screen name (@ handle) of the Twitter user.

        - return: The numeric user ID (`rest_id`) of the specified user.
        """
        try:
            data = self.user_by_screen_name(screen_name)
            return data["data"]["user"]["result"]["rest_id"]
        except HTTPError:
            logging.warning("Trying with backup endpoint")
            data = self.profile_spotlights_query(screen_name)
            return data["data"]["user_result_by_screen_name"]["result"]["rest_id"]

    def user_tweets(self, user_id, number_of_tweets):
        query_id = "HuTx74BxAnezK1gWvYY7zg"
        operation_name = "UserTweets"
        variables = {
            'userId': user_id,
            'count': number_of_tweets,
            "withTweetQuoteCount": True,
            "includePromotedContent": True,
            "withQuickPromoteEligibilityTweetFields": False,
            "withSuperFollowsUserFields": True,
            "withUserResults": True,
            "withNftAvatar": False,
            "withBirdwatchPivots": False,
            "withReactionsMetadata": False,
            "withReactionsPerspective": False,
            "withSuperFollowsTweetFields": True,
            "withVoice": True,
        }
        features = '{}'
        return self.get(query_id, operation_name, variables, features)

    def user_by_id(self, user_id):
        query_id = "GazOglcBvgLigl3ywt6b3Q"
        operation_name = "UserByRestId"
        variables = {
            'userId': user_id,
            "withSafetyModeUserFields": False,
            "withSuperFollowsUserFields": False,
            "withVoice": True
        }
        features = '{}'
        return self.get(query_id, operation_name, variables, features)

    def user_id_from_url(self, user_url: str) -> str:
        """Retrieve the numeric user ID (`rest_id`) of the user that the specified profile URL linked to.

        Supported URL formats:
        - https://twitter.com/<screen_name>
        - http://twitter.com/<screen_name>
        - twitter.com/<screen_name>
        and with any number of trailing slashes (`/`).

        - user_url: The URL pointing to the profile of the Twitter user.

        - return: The numeric user ID (`rest_id`) of the specified user.

        - raise RuntimeError: If the specified URL is not a valid Twitter user profile URL.
        """
        if match := re.match(
                r"^(?:https?:\/\/|)(?:twitter|x)\.com\/(?P<screen_name>\w+)$", user_url.strip("/")
        ):
            return self.user_id(match.group("screen_name"))
        raise RuntimeError(f"Invalid Twitter user URL: {user_url}")

    def tweet_by_id(self, tweet_id, cursor=None):
        query_id = "_8aYOgEDz35BrBcBal1-_w"
        operation_name = "TweetDetail"

        variables = {
            "focalTweetId": tweet_id,
            "with_rux_injections": False,
            "rankingMode": "Relevance",
            "includePromotedContent": True,
            "withCommunity": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withBirdwatchNotes": True,
            "withVoice": True
        }

        features = {
            "rweb_video_screen_enabled": False,
            "profile_label_improvements_pcf_label_in_post_enabled": True,
            "rweb_tipjar_consumption_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "premium_content_api_read_enabled": False,
            "communities_web_enable_tweet_community_results_fetch": True,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
            "responsive_web_grok_analyze_post_followups_enabled": True,
            "responsive_web_jetfuel_frame": False,
            "responsive_web_grok_share_attachment_enabled": True,
            "articles_preview_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False,
            "responsive_web_grok_show_grok_translated_post": False,
            "responsive_web_grok_analysis_button_from_backend": True,
            "creator_subscriptions_quote_tweet_preview_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "responsive_web_grok_image_annotation_enabled": True,
            "responsive_web_enhance_cards_enabled": False
        }

        field_toggles = {
            "withArticleRichContentState": True,
            "withArticlePlainText": False,
            "withGrokAnalyze": False,
            "withDisallowedReplyControls": False
        }

        return self.get(query_id, operation_name, variables, features, field_toggles)

    def get_cookie_dict(self, path):
        cookies = {}
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('\t')
                if len(parts) != 7:
                    # not a valid cookie line
                    continue

                name = parts[5]
                raw_value = parts[6]
                if raw_value.startswith('"') and raw_value.endswith('"'):
                    raw_value = raw_value[1:-1]
                value = urllib.parse.unquote(raw_value)
                cookies[name] = value
        return cookies

    def tweet_text_by_url(self, tweet_url: str, cookies_path) -> str:
        import requests
        tweet_id = re.search(r"status/(\d+)", tweet_url).group(1)
        url = "https://x.com/i/api/graphql/_8aYOgEDz35BrBcBal1-_w/TweetDetail"
        params = {
            "variables": '{"focalTweetId":tweet_id,"with_rux_injections":false,"rankingMode":"Relevance","includePromotedContent":true,"withCommunity":true,"withQuickPromoteEligibilityTweetFields":true,"withBirdwatchNotes":true,"withVoice":true}',
            "features": '{"rweb_video_screen_enabled":false,"profile_label_improvements_pcf_label_in_post_enabled":true,"rweb_tipjar_consumption_enabled":true,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"premium_content_api_read_enabled":false,"communities_web_enable_tweet_community_results_fetch":true,"c9s_tweet_anatomy_moderator_badge_enabled":true,"responsive_web_grok_analyze_button_fetch_trends_enabled":false,"responsive_web_grok_analyze_post_followups_enabled":true,"responsive_web_jetfuel_frame":false,"responsive_web_grok_share_attachment_enabled":true,"articles_preview_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":true,"tweet_awards_web_tipping_enabled":false,"responsive_web_grok_show_grok_translated_post":false,"responsive_web_grok_analysis_button_from_backend":true,"creator_subscriptions_quote_tweet_preview_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_grok_image_annotation_enabled":true,"responsive_web_enhance_cards_enabled":false}',
            "fieldToggles": '{"withArticleRichContentState":true,"withArticlePlainText":false,"withGrokAnalyze":false,"withDisallowedReplyControls":false}'
        }
        params['variables'] = params['variables'].replace('tweet_id', tweet_id)

        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
            "Content-Type": "application/json",
            "Referer": tweet_url,
            "Sec-CH-UA": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "X-Client-Transaction-Id": "tA5vYayNBAqFK3QWjvLzdAawt9ETc7zV/8lv41a5a85d84SqSVXYjeH8+ijVcHNQF+z5dLeA/fFb7O0u1P39ZXcynFuwtw",
            "X-Client-UUID": "3cf67b4d-737f-4e0e-b39b-b22939dcf33c",
            "X-CSRF-Token": "4ee4ed3dee598a39fe1c871ac71973dba89ae44777f3cdeb6564ec2713fc3096744f4d7649d5896fcd651b83438b58c3eabef6adce8c4d37c0afdefdfd4a561771093dbf4b6bd1d2d0e90ba5a268f1cc",
            "X-Twitter-Active-User": "yes",
            "X-Twitter-Auth-Type": "OAuth2Session",
            "X-Twitter-Client-Language": "en"
        }

        # If you need to send cookies separately:

        cookies = self.get_cookie_dict(cookies_path)
        headers["X-CSRF-Token"] = cookies["ct0"]
        response = requests.get(url, headers=headers, params=params, cookies=cookies)
        success = response.status_code == 200
        return response.text, success


class FleetsAPI(APIClient):
    """Twitter Fleets API client."""

    def __init__(self, client: HTTPClient, path: str, cookies: dict[str, str]) -> None:
        """Initialize the Twitter Fleets API client.

        - client: The `HTTPClient` instance to send requests.
        - path: The path to add to the base URL of the API.
        - cookies: The cookies used for making all requests to the API.
        """
        super().__init__(client, path, cookies)

    def get(self, version: str, endpoint: str, params: dict[str, str]) -> Any:
        """Send HTTP GET requests to the Twitter Fleets API.

        - version: The version of the API.
        - endpoint: The endpoint of the API.
        - params: Query parameters of the request.

        - return: The object returned in the response of the API.
        """
        return super().get(self.join_url(version, endpoint), params)

    def avatar_content(self, *user_ids: str) -> dict:
        """Retrieve Twitter Space details of the specified user IDs.

        This endpoint limits to a maximum of 100 user IDs per request.

        - user_ids: Numeric user IDs (`rest_id`) of users.

        - return: Twitter Space details of the specified user IDs. Only ongoing Twitter Spaces will be returned.
        """
        if len(user_ids) > 100:
            raise RuntimeError(
                "Number of user IDs exceeded the limit of 100 per request"
            )
        version = "v1"
        endpoint = "avatar_content"
        params = {"user_ids": ",".join(user_ids), "only_spaces": "true"}
        return self.get(version, endpoint, params)


class LiveVideoStreamAPI(APIClient):
    """Twitter Live Video Stream API client."""

    def __init__(self, client: HTTPClient, path: str, cookies: dict[str, str]) -> None:
        """Initialize the Twitter Live Video Stream API client.

        - client: The `HTTPClient` instance to send requests.
        - path: The path to add to the base URL of the API.
        - cookies: The cookies used for making all requests to the API.
        """
        super().__init__(client, path, cookies)

    def status(self, media_key: str) -> dict:
        """Retrieve Twitter Space media playlist details by the specified media key.

        - media_key: The media key of the Twitter Space.

        - return: The media playlist details of the specified media key.

        """
        url = f"https://x.com/i/api/1.1/live_video_stream/status/{media_key}"
        params = {
            "client": "web",
            "use_syndication_guest_id": "false",
            "cookie_set_host": "x.com"
        }

        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Authorization": TWITTER_AUTHORIZATION,
            "Content-Type": "application/json",
            "Referer": "https://x.com/home",
            "Sec-CH-UA": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Linux"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "X-Twitter-Active-User": "yes",
            "X-Twitter-Auth-Type": "OAuth2Session",
            "X-Twitter-Client-Language": "en"
        }

        cookies = self.cookies
        headers["X-CSRF-Token"] = cookies["ct0"]
        response = requests.get(url, headers=headers, params=params, cookies=cookies)

        return response.json()


class DummyAPI:
    """Dummy API class used for uninitialized APIs."""

    def __init__(self, api_name: str = "API") -> None:
        self.api_name = api_name

    def __getattr__(self, name: str) -> NoReturn:
        """Show a clear message to the user if the API was not initialized.

        - raise RuntimeError: If any attribute of the class is accessed or any method is called.
        """
        raise RuntimeError(f"{self.api_name} is not initialized")

    def __bool__(self) -> False:
        """Always evaluate instances of the class to `False`.

        This is just for the convenience of testing the instance directly in `if` statements:
        >>> api = DummyAPI()
        ... if api:  # non-dummy API instances would evaluate to `True`
        ...     # do something if the API was initialized
        ...     pass
        See also: `TwitterAPI.__bool__()`

        - return: `False`.
        """
        return False


class TwitterAPI:
    """The collection of all Twitter APIs."""

    def __init__(self) -> None:
        """Initialize the instance of the Twitter API collection.

        Note that this will not initialize APIs in this collection. They will initially only be an
        instance of the `DummyAPI` class.
        They need to be initialized by calling the `init_apis()` method with cookies of the user.
        """
        self.client = HTTPClient()
        self.graphql_api = DummyAPI("Twitter GraphQL API")
        self.fleets_api = DummyAPI("Twitter Fleets API")
        self.live_video_stream_api = DummyAPI("Twitter Live Video Stream API")

    def init_apis(self, cookies: dict[str, str]) -> None:
        """Initialize all APIs in this collection with the specified cookies."""
        self.graphql_api = GraphQLAPI(self.client, "graphql", cookies)
        self.fleets_api = FleetsAPI(self.client, "fleets", cookies)
        self.live_video_stream_api = LiveVideoStreamAPI(
            self.client, "1.1/live_video_stream", cookies
        )

    def __bool__(self) -> bool:
        """Determine if all APIs are initialized.

        This is just for the convenience of testing the instance directly in `if` statements:
        >>> api = TwitterAPI()
        ... if api:
        ...     print("API initialized")  # would run if all APIs in the `api` instance are initialized
        See also: `DummyAPI.__bool__()`

        - return: `True` if and only if all APIs are initialized, `False` otherwise.
        """
        return bool(self.graphql_api and self.fleets_api and self.live_video_stream_api)


"""The global instance of the collection of Twitter APIs."""
API = TwitterAPI()
