from django.utils import timezone


class UploadTiming:
    """Record the earliest request moment: CSRF (and any body-consuming middleware) reads the
    uploaded recording before the view runs, so transfer+staging must anchor before them."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.upload_started_wall = timezone.now()
        return self.get_response(request)


class PrivatePages:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/static/"):
            response["Cache-Control"] = "no-store, private"
            response["Referrer-Policy"] = "same-origin"
            response["Permissions-Policy"] = "microphone=(self), camera=()"
            response["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response
