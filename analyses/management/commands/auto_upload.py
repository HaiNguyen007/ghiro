# Ghiro - Copyright (C) 2013-2016 Ghiro Developers.
# This file is part of Ghiro.
# See the file 'docs/LICENSE.txt' for license terms.

import os
import re
import logging
import shutil
import sys
from time import sleep
from django.conf import settings
from django.core.management.base import NoArgsCommand
from django.core.exceptions import ObjectDoesNotExist

from analyses.models import Analysis, Case

logger = logging.getLogger(__name__)

class Command(NoArgsCommand):
    """Monitor a directory for new files."""

    help = "Directory monitor and images upload."

    option_list = NoArgsCommand.option_list

    @staticmethod
    def create_auto_upload_dirs():
        """Creates the directory tree used in upload from file system feature.
        It creates the AUTO_UPLOAD_DIR directory and a folder for each case with the Syntax 'Case_id_1' where 1 is
        the case ID.
        Folders have the following structure:
            AUTO_UPLOAD_DIR
                |
                |--- Case_id_1
                |--- Case_id_2
                |--- etc. (one for each case)
        """
        # Sync cases if auto upload is enabled.
        if settings.AUTO_UPLOAD_DIR:
            logger.debug("Auto upload from directory is enabled on %s.", settings.AUTO_UPLOAD_DIR)

            # Cleanup auto upload directory:
            if settings.AUTO_UPLOAD_STARTUP_CLEANUP and os.path.exists(settings.AUTO_UPLOAD_DIR):
                logger.debug("Cleaning up %s.", settings.AUTO_UPLOAD_DIR)
                try:
                    shutil.rmtree(settings.AUTO_UPLOAD_DIR)
                except IOError as e:
                    logger.error("Unable to clean auto upload directory %s reason %s" % (settings.AUTO_UPLOAD_DIR, e))
                    return False

            # Create directory if it's missing.
            if not os.path.exists(settings.AUTO_UPLOAD_DIR):
                logger.debug("Auto upload directory is missing, creating it.")
                try:
                    os.mkdir(settings.AUTO_UPLOAD_DIR)
                except IOError as e:
                    logger.error("Unable to create auto upload main directory %s reason %s" % (settings.AUTO_UPLOAD_DIR, e))
                    return False

            # Create cases dirs.
            for case in Case.objects.all():
                dir_path = os.path.join(settings.AUTO_UPLOAD_DIR, case.directory_name)
                if not os.path.exists(dir_path):
                    try:
                        logger.debug("Creating directory %s" % dir_path)
                        os.mkdir(dir_path)
                    except IOError as e:
                        logger.error("Unable to create auto upload case directory %s reason %s" % (dir_path, e))
                        continue
        else:
            return False

    def handle(self, *args, **options):
        """Runs command."""
        logger.debug("Starting directory monitoring...")

        # Path.
        monitor_path = settings.AUTO_UPLOAD_DIR
        # Preventive check.
        if not monitor_path:
            logger.error("Missing AUTO_UPLOAD_DIR in your configuration file, aborting.")
            sys.exit()

        logger.info("Monitoring directory %s" % monitor_path)

        try:
            self.run(monitor_path)
        except KeyboardInterrupt:
            print("Exiting... (requested by user)")

    def submit_file(self, path, case):
        """Submit a file for analysis.
        @param path: file path
        @param case: case instance
        """
        # Submit.
        Analysis.add_task(path, case=case, user=case.owner)
        # Delete original file:
        if settings.AUTO_UPLOAD_DEL_ORIGINAL:
            os.remove(path)

    def parse_dir_name(self, path):
        """Parses case directory name.
        @param path: directory path.
        @return: case instance
        """
        # Regexp on folder name.
        case_match = re.search("Case_id_([\d]+)$", path)
        try:
            case_id = case_match.group(1)
        except AttributeError:
            return None

        # Search.
        try:
            case = Case.objects.get(pk=case_id)
        except ObjectDoesNotExist:
            return None
        else:
            return case

    def run(self, path, sleep_time=30):
        """Starts directory monitoring for new images.
        @param path: auto upload directory path"""
        # Create tree.
        self.create_auto_upload_dirs()
        # List of already scanned files.
        files_found = []

        # Antani loop.
        while True:
            for dir_name, dir_names, file_names in os.walk(path):
                for file_name in file_names:
                    target = os.path.join(dir_name, file_name)
                    # Check if already scanned.
                    if not target in files_found:
                        logger.debug("Found new file %s" % target)

                        # Parse case ID from directory name.
                        case = self.parse_dir_name(dir_name)
                        if case:
                            # Submit image.
                            self.submit_file(target, case)

            # Check for removed files.
            for file in files_found:
                if not os.path.exists(file):
                    files_found.remove(file)

            # Wait for next cycle.
            sleep(sleep_time)