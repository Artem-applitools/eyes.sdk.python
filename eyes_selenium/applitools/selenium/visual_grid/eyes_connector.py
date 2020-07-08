import typing

from requests.adapters import HTTPAdapter

from applitools.common import (
    AppEnvironment,
    AppOutput,
    EyesError,
    RectangleSize,
    Region,
    VisualGridSelector,
    logger,
)
from applitools.common.ultrafastgrid import (
    RenderRequest,
    RunningRender,
    VGResource,
    IRenderBrowserInfo,
)
from applitools.core import NULL_REGION_PROVIDER, EyesBase, RegionProvider
from applitools.core.capture import AppOutputWithScreenshot
from applitools.core.server_connector import ClientSession, ServerConnector
from applitools.selenium import Configuration
from applitools.selenium.__version__ import __version__

if typing.TYPE_CHECKING:
    from typing import Text, List, Dict, Any, Optional
    from requests import Response
    from applitools.common.ultrafastgrid import (
        RenderingInfo,
        RenderBrowserInfo,
        RenderStatusResults,
    )
    from applitools.common.match import MatchResult
    from applitools.common.test_results import TestResults
    from applitools.selenium.fluent import SeleniumCheckSettings


class VGClientSession(ClientSession):
    SESSION_POOL_CONNECTIONS = 32
    SESSION_MAX_POOL_SIZE = SESSION_POOL_CONNECTIONS + 4

    def __init__(self):
        super(VGClientSession, self).__init__()
        self._session.mount(
            "https://",
            HTTPAdapter(
                pool_connections=self.SESSION_POOL_CONNECTIONS,
                pool_maxsize=self.SESSION_MAX_POOL_SIZE,
            ),
        )
        self._session.mount(
            "http://",
            HTTPAdapter(
                pool_connections=self.SESSION_POOL_CONNECTIONS,
                pool_maxsize=self.SESSION_MAX_POOL_SIZE,
            ),
        )


class EyesConnector(EyesBase):
    _session_cls = VGClientSession

    def __init__(self, browser_info, config, ua_string, rendering_info):
        # type: (RenderBrowserInfo,Configuration,Text,Optional[RenderingInfo])->None
        super(EyesConnector, self).__init__()
        self._current_uuid = None
        self._region_selectors = None
        self._regions = None
        self._render_statuses = {}  # type: Dict[Text, RenderStatusResults]

        self.device_name = getattr(browser_info, "device_name", None)
        self._browser_info = browser_info  # type: IRenderBrowserInfo
        self._ua_string = ua_string
        self.set_configuration(config)
        self._server_connector.update_config(
            config, self.full_agent_id, rendering_info, ua_string
        )

    def open(self, config):
        # type: (Configuration) -> None
        """Starts a new test without setting the viewport size of the AUT."""
        logger.info(
            "opening EyesConnector with viewport size: {}".format(
                self._browser_info.viewport_size
            )
        )
        self._config = config.clone()
        if self.device_name and self.render_status.device_size:
            self._config.viewport_size = self.render_status.device_size
        else:
            self._config.viewport_size = self._browser_info.viewport_size

        self._config.baseline_env_name = self._browser_info.baseline_env_name
        self._open_base()

    def render_put_resource(self, running_render, resource):
        # type: (RunningRender, VGResource) -> Text
        return self._server_connector.render_put_resource(running_render, resource)

    def render(self, *render_requests):
        # type: (*RenderRequest) -> List[RunningRender]
        return self._server_connector.render(*render_requests)

    def render_status_by_id(self, *render_ids):
        # type: (*Text) -> List[RenderStatusResults]
        return self._server_connector.render_status_by_id(*render_ids)

    def download_resource(self, url):
        # type: (Text) -> Response
        return self._server_connector.download_resource(url)

    @property
    def base_agent_id(self):
        # type: () -> Text
        return "eyes.selenium.visualgrid.python/{}".format(__version__)

    def _try_capture_dom(self):
        return None

    def get_viewport_size(self):
        return None

    def set_viewport_size(self, size):
        return None

    def _get_viewport_size(self):
        return None

    def _set_viewport_size(self, size):
        # type: (RectangleSize) -> Optional[Any]
        return None

    @property
    def _inferred_environment(self):
        # type: () -> str
        return ""

    def _get_screenshot(self):
        return None

    @property
    def _title(self):
        # type: () -> Text
        return ""

    @property
    def _environment(self):
        # type: () -> AppEnvironment
        app_env = AppEnvironment(
            display_size=self.render_status.device_size,
            inferred="useragent: {}".format(self.render_status.user_agent),
            device_info=self.device_name,
        )
        return app_env

    def render_info(self):
        # type: () -> RenderingInfo
        return self._server_connector.render_info()

    def check(
        self,
        name,  # type: Text
        check_settings,  # type: SeleniumCheckSettings
        check_task_uuid,  # type:  Text
        region_selectors,  # type: List[VisualGridSelector]
        regions,  # type: List[Region]
    ):
        # type:(...)->MatchResult
        self._current_uuid = check_task_uuid
        if name:
            check_settings = check_settings.with_name(name)
        logger.debug("EyesConnector.check({}, {})".format(name, check_task_uuid))
        self._region_selectors = region_selectors
        self._regions = regions
        check_result = self._check_window_base(
            NULL_REGION_PROVIDER, name, False, check_settings
        )
        self._current_uuid = None
        self._region_selectors = []
        self._regions = []
        return check_result

    def close(self, raise_ex=True):
        # type: (bool) -> TestResults
        self._current_uuid = None
        return super(EyesConnector, self).close(raise_ex)

    def render_status_for_task(self, uuid, status):
        # type: (str, RenderStatusResults) -> None
        self._current_uuid = uuid
        self._render_statuses[uuid] = status

    @property
    def render_status(self):
        # type: ()->RenderStatusResults
        status = self._render_statuses.get(self._current_uuid)
        logger.debug("task.uuid: {}, status: {}".format(self._current_uuid, status))
        if not status:
            raise EyesError(
                "Got empty render status with key {}!".format(self._current_uuid)
            )
        return status

    def _match_window(self, region_provider, tag, ignore_mismatch, check_settings):
        # type: (RegionProvider, Text, bool, SeleniumCheckSettings) -> MatchResult
        # Update retry timeout if it wasn't specified.
        retry_timeout_ms = -1  # type: int
        if check_settings:
            retry_timeout_ms = check_settings.values.timeout

        region = region_provider.get_region()
        logger.debug("params: ([{}], {}, {} ms)".format(region, tag, retry_timeout_ms))

        app_output = self._get_app_output_with_screenshot(None, None, check_settings)
        image_match_settings = self._match_window_task.create_image_match_settings(
            check_settings, self
        )
        return self._match_window_task.perform_match(
            app_output=app_output,
            name=tag,
            ignore_mismatch=ignore_mismatch,
            image_match_settings=image_match_settings,
            eyes=self,
            user_inputs=self._user_inputs,
            check_settings=check_settings,
            render_id=self.render_status.render_id,
            region_selectors=self._region_selectors,
            regions=self._regions,
        )

    def _get_app_output_with_screenshot(self, region, last_screenshot, check_settings):
        # type: (None, None, SeleniumCheckSettings)->AppOutputWithScreenshot
        logger.debug("render_task.uuid: {}".format(self._current_uuid))
        app_output = AppOutput(
            title=self._title,
            screenshot_bytes=None,
            screenshot_url=self.render_status.image_location,
            dom_url=self.render_status.dom_location,
        )
        result = AppOutputWithScreenshot(app_output, None)
        return result
