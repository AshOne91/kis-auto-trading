from kis_auto_trading.application.app_factory import create_app
from kis_auto_trading.modules.signal.generated.router import (
    router as signal_router,
)

app = create_app(
    module_routers=(
        signal_router,
    ),
    include_user_routers=False,
)
