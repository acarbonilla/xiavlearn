from rest_framework.response import Response
from rest_framework.views import exception_handler


def success_response(data, message, status_code=200):
    return Response(
        {
            'success': True,
            'data': data,
            'message': message,
        },
        status=status_code,
    )


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    error = response.data
    if isinstance(error, dict) and set(error) == {'detail'}:
        error = str(error['detail'])

    response.data = {
        'success': False,
        'error': error,
    }
    return response
