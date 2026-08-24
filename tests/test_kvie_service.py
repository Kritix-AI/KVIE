from Backend.kvie.service import app


def test_streaming_service_exposes_health_and_websocket_routes():
    routes = {getattr(route, "path", None) for route in app.routes}
    assert "/health" in routes
    assert "/ws/transcribe" in routes
