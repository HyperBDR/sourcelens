#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    # 确保我们在正确的目录下运行
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)

    # 将当前目录添加到 Python 路径
    sys.path.insert(0, project_root)

    os.environ.setdefault(
        'DJANGO_SETTINGS_MODULE',
        'core.settings'
    )
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
