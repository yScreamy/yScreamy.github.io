from hyperliquid.info import Info
import config

info = Info(config.BASE_URL, skip_ws=True)
state = info.user_state(config.WALLET_ADDRESS)

print("BASE_URL:", config.BASE_URL)
print("WALLET:", config.WALLET_ADDRESS)
print("marginSummary:", state.get("marginSummary"))
print("crossMarginSummary:", state.get("crossMarginSummary"))
print("assetPositions count:", len(state.get("assetPositions", [])))
