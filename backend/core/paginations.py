"""
Global Pagination Configuration

This module provides a unified pagination configuration for the entire project
using Django REST Framework's PageNumberPagination. It ensures consistent
pagination behavior across all API endpoints.

Usage:
    To use this pagination in your views, either:
    1. Set it globally in REST_FRAMEWORK settings:
        REST_FRAMEWORK = {
            'DEFAULT_PAGINATION_CLASS': 'core.paginations.APIPagination',
            'PAGE_SIZE': 10
        }
    2. Or apply it to specific views using the pagination_class attribute:
        class MyViewSet(ViewSet):
            pagination_class = APIPagination

Query Parameters:
    - page: The page number (e.g., ?page=2)
    - page_size: Number of items per page (e.g., ?page_size=20)
"""

from rest_framework.pagination import PageNumberPagination


class APIPagination(PageNumberPagination):
    """
    A custom pagination class that provides standardized pagination settings.

    Attributes:
        page_size: Number of items to return per page
        page_size_query_param: Query parameter to specify page size
        max_page_size: Maximum allowed page size
        page_query_param: Query parameter for page number
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 10000
    page_query_param = 'page'