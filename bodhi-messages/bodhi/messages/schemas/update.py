# Copyright (C) 2018-2019 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""
Message schema for Updates.

Each message is defined as a Python class. For details, see `fedora-messaging
<https://fedora-messaging.readthedocs.io/en/stable/>`_ documentation on
messages.
"""

import copy
import typing

from fedora_messaging.message import DEBUG

from ..utils import past_tense, truncate
from .base import BodhiMessage, BuildV1, ReleaseV1, SCHEMA_URL, UpdateV1, UserV1


class UpdateMessage(BodhiMessage):
    """Base class for update messages."""

    @property
    def url(self) -> str:
        """
        Return a URL to the action that caused this message to be emitted.

        Returns:
            A relevant URL.
        """
        return f"https://bodhi.fedoraproject.org/updates/{self.update.alias}"

    @property
    def update(self) -> UpdateV1:
        """Return the Update referenced by this message."""
        # Many things use this object, so let's cache it so we don't construct it repeatedly.
        if not hasattr(self, '_update_obj'):
            self._update_obj = UpdateV1(
                self._update['alias'], [BuildV1(b['nvr']) for b in self._update['builds']],
                UserV1(self._update['user']['name']), self._update['status'],
                self._update['request'], ReleaseV1(self._update['release']['name']))
        return self._update_obj

    @property
    def usernames(self) -> typing.List[str]:
        """
        List of users affected by the action that generated this message.

        Returns:
            A list of affected usernames.
        """
        usernames = super(UpdateMessage, self).usernames
        # Add the submitter if there is one
        if self.update.user.name not in usernames:
            usernames.append(self.update.user.name)
        usernames.sort()
        return usernames

    @property
    def packages(self) -> typing.Iterable[str]:
        """
        List of names of packages affected by the action that generated this message.

        Returns:
            A list of affected package names.
        """
        return self.update.packages

    @property
    def _update(self) -> dict:
        """Return a dictionary from the body representing an update."""
        return self.body['update']

    @property
    def _builds_summary(self):
        """Return a truncated list of the update's builds."""
        return truncate(' '.join([b.nvr for b in self.update.builds]))

    @property
    def _owner_qual(self):
        """Return a string to qualify whether the update belongs to the agent."""
        if self.agent_name == self.update.user.name:
            return "their"
        else:
            return f"{self.update.user.name}'s"

    def __str__(self) -> str:
        """
        Return a human-readable representation of this message.

        This should provide a detailed representation of the message, much like the body
        of an email.

        Returns:
            A human readable representation of this message.
        """
        return self.summary


class UpdateCommentV1(UpdateMessage):
    """Sent when a comment is made on an update."""

    body_schema = {
        'id': f'{SCHEMA_URL}/v1/bodhi.update.comment#',
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'description': 'Schema for message sent when a comment is added to an update',
        'type': 'object',
        'properties': {
            'comment': {
                'type': 'object',
                'description': 'The comment added to an update',
                'properties': {
                    'karma': {
                        'type': 'integer',
                        'description': 'The karma associated with the comment',
                    },
                    'text': {
                        'type': 'string',
                        'description': 'The text of the comment',
                    },
                    'timestamp': {
                        'type': 'string',
                        'description': 'The timestamp that the comment was left on.'
                    },
                    'update': UpdateV1.schema(),
                    'user': UserV1.schema(),
                },
                'required': ['karma', 'text', 'timestamp', 'update', 'user'],
            },
        },
        'required': ['comment'],
        'definitions': {
            'build': BuildV1.schema(),
        }
    }

    topic = "bodhi.update.comment"

    def __str__(self) -> str:
        """
        Return a human-readable representation of this message.

        This should provide a detailed representation of the message, much like the body
        of an email.

        Returns:
            A human readable representation of this message.
        """
        new_line = "\n"
        return (
            f"{self.user.name} commented on {self.update.user.name}'s "
            f"update {self.update.alias} with karma {self.karma}:\n\n"
            f"{self.body['comment']['text']}\n\n"
            "Builds:\n"
            f"{new_line.join([b.nvr for b in self.update.builds])}"
        )

    @property
    def karma(self) -> int:
        """Return the karma from this comment."""
        return self.body['comment']['karma']

    @property
    def summary(self) -> str:
        """
        Return a short, human-readable representation of this message.

        This should provide a short summary of the message, much like the subject line
        of an email.

        Returns:
            A summary for this message.
        """
        return (f"{self.user.name} commented on update {self._builds_summary} "
                f"(karma: {self.karma})")

    @property
    def agent_name(self) -> str:
        """
        Return the agent's username for this message.

        Returns:
            The agent's username.
        """
        return self.user.name

    @property
    def user(self) -> UserV1:
        """Return the user who wrote this comment."""
        return UserV1(self.body['comment']['user']['name'])

    @property
    def _update(self) -> dict:
        """Return a dictionary from the body representing an update."""
        return self.body['comment']['update']


class UpdateCompleteStableV1(UpdateMessage):
    """Sent when an update is available in the stable repository."""

    body_schema = {
        'id': f'{SCHEMA_URL}/v1/bodhi.update.complete.stable#',
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'description': 'Schema for message sent when an update is pushed stable',
        'type': 'object',
        'properties': {
            'update': UpdateV1.schema(),
        },
        'required': ['update'],
        'definitions': {
            'build': BuildV1.schema(),
        }
    }

    topic = "bodhi.update.complete.stable"

    @property
    def summary(self) -> str:
        """
        Return a short, human-readable representation of this message.

        This should provide a short summary of the message, much like the subject line
        of an email.

        Returns:
            A summary for this message.
        """
        return (
            f"{self.update.user.name}'s {self._builds_summary} "
            f"bodhi update completed push to {self.update.status}")

    def __str__(self) -> str:
        """
        Return a human-readable representation of this message.

        This should provide a detailed representation of the message, much like the body
        of an email.

        Returns:
            A human readable representation of this message.
        """
        new_line = "\n"
        return (
            f"{self.update.user.name}'s Bodhi update {self.update.alias} "
            f"completed push to {self.update.status}\n"
            f"Builds:\n"
            f"{new_line.join([b.nvr for b in self.update.builds])} ")


class UpdateCompleteTestingV1(UpdateMessage):
    """Sent when an update is available in the testing repository."""

    body_schema = {
        'id': f'{SCHEMA_URL}/v1/bodhi.update.complete.testing#',
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'description': 'Schema for message sent when an update is pushed to testing',
        'type': 'object',
        'properties': {
            'update': UpdateV1.schema(),
        },
        'required': ['update'],
        'definitions': {
            'build': BuildV1.schema(),
        }
    }

    topic = "bodhi.update.complete.testing"

    @property
    def summary(self) -> str:
        """
        Return a short, human-readable representation of this message.

        This should provide a short summary of the message, much like the subject line
        of an email.

        Returns:
            A summary for this message.
        """
        return (
            f"{self.update.user.name}'s {self._builds_summary} "
            f"bodhi update completed push to {self.update.status}")

    def __str__(self) -> str:
        """
        Return a human-readable representation of this message.

        This should provide a detailed representation of the message, much like the body
        of an email.

        Returns:
            A human readable representation of this message.
        """
        new_line = "\n"
        return (
            f"{self.update.user.name}'s Bodhi update {self.update.alias} "
            f"completed push to {self.update.status}\n"
            f"Builds:\n"
            f"{new_line.join([b.nvr for b in self.update.builds])} ")


class UpdateEditV1(UpdateMessage):
    """Sent when an update is edited."""

    body_schema = {
        'id': f'{SCHEMA_URL}/v1/bodhi.update.edit#',
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'description': 'Schema for message sent when an update is edited',
        'type': 'object',
        'properties': {
            'agent': {
                'type': 'string',
                'description': 'The user who edited the update',
            },
            'new_bugs': {
                'type': 'array',
                'description': 'An array of bug ids that have been added to the update',
                'items': {
                    'type': 'integer',
                    'description': 'A Bugzilla bug ID'
                }
            },
            'update': UpdateV1.schema(),
        },
        'required': ['agent', 'new_bugs', 'update'],
        'definitions': {
            'build': BuildV1.schema(),
        }
    }

    topic = "bodhi.update.edit"

    @property
    def new_bugs(self) -> typing.Iterable[int]:
        """
        Return an iterable of the new bugs that have been added to the update.

        Returns:
            A list of Bugzilla bug IDs.
        """
        return self.body['new_bugs']

    @property
    def summary(self) -> str:
        """
        Return a short, human-readable representation of this message.

        This should provide a short summary of the message, much like the subject line
        of an email.

        Returns:
            A summary for this message.
        """
        return (
            f"{self.agent_name} edited {self._owner_qual} update {self.update.alias} "
            f"({self._builds_summary})"
        )

    def __str__(self) -> str:
        """
        Return a human-readable representation of this message.

        This should provide a detailed representation of the message, much like the body
        of an email.

        Returns:
            A human readable representation of this message.
        """
        return (
            f"{self.agent_name} edited {self.update.alias} "
            f"adding {len(self.body['new_bugs'])} new bugs"
        )


class UpdateEditV2(UpdateEditV1):
    """
    Sent when an update is edited. Newer version.

    Has 'new_builds' and 'removed_builds' properties.
    """

    # mypy infers that lots of the things we touch below should be
    # collections of strings and doesn't like us doing unexpected
    # things to them, so the typing.Any shuts it up
    body_schema: typing.Any = copy.deepcopy(UpdateEditV1.body_schema)
    body_schema['properties']['new_builds'] = {
        'type': 'array',
        'description': 'An array of build NVRs that have been added to the update',
        'items': {
            'type': 'string',
            'description': 'A build NVR'
        }
    }
    body_schema['properties']['removed_builds'] = {
        'type': 'array',
        'description': 'An array of build NVRs that have been removed from the update',
        'items': {
            'type': 'string',
            'description': 'A build NVR'
        }
    }
    body_schema['required'].extend(('new_builds', 'removed_builds'))

    def __str__(self) -> str:
        """
        Return a human-readable representation of this message.

        This should provide a detailed representation of the message, much like the body
        of an email.

        Returns:
            A human readable representation of this message.
        """
        return (
            f"{self.agent_name} edited {self.update.alias} "
            f"adding {len(self.body['new_bugs'])} new bug(s), "
            f"adding {len(self.body['new_builds'])} build(s), and "
            f"removing {len(self.body['removed_builds'])} build(s)"
        )


class UpdateEjectV1(UpdateMessage):
    """Sent when an update is ejected from the push."""

    body_schema = {
        'id': f'{SCHEMA_URL}/v1/bodhi.update.eject#',
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'description': 'Schema for message sent when an update is ejected from a compose',
        'type': 'object',
        'properties': {
            'reason': {
                'type': 'string',
                'description': 'The reason the update was ejected',
            },
            'repo': {
                'type': 'string',
                'description': 'The name of the repo that the update is associated with'
            },
            'update': UpdateV1.schema(),
        },
        'required': ['reason', 'repo', 'update'],
        'definitions': {
            'build': BuildV1.schema(),
        }
    }

    topic = "bodhi.update.eject"

    @property
    def reason(self) -> str:
        """Return the reason this update was ejected from the compose."""
        return self.body['reason']

    @property
    def repo(self) -> str:
        """Return the name of the repository that this update is associated with."""
        return self.body['repo']

    @property
    def summary(self) -> str:
        """
        Return a short, human-readable representation of this message.

        This should provide a short summary of the message, much like the subject line
        of an email.

        Returns:
            A summary for this message.
        """
        return (
            f"{self.update.user.name}'s {self._builds_summary} "
            f"bodhi update was ejected from the {self.repo} mash. Reason: \"{self.reason}\"")


class UpdateKarmaThresholdV1(UpdateMessage):
    """Sent when an update reaches its karma threshold."""

    body_schema = {
        'id': f'{SCHEMA_URL}/v1/bodhi.update.karma.threshold.reach#',
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'description': 'Schema for message sent when an update reaches its karma threshold',
        'type': 'object',
        'properties': {
            'status': {
                'type': 'string',
                'description': 'Which karma threshold was reached',
                'enum': ['stable', 'unstable']
            },
            'update': UpdateV1.schema(),
        },
        'required': ['status', 'update'],
        'definitions': {
            'build': BuildV1.schema(),
        }
    }

    topic = "bodhi.update.karma.threshold.reach"

    @property
    def status(self) -> str:
        """Return the threshold that was reached."""
        return self.body['status']

    @property
    def summary(self) -> str:
        """
        Return a short, human-readable representation of this message.

        This should provide a short summary of the message, much like the subject line
        of an email.

        Returns:
            A summary for this message.
        """
        return (
            f"{self.update.user.name}'s {self._builds_summary} bodhi update "
            f"has reached the {self.status} karma threshold"
        )

    def __str__(self) -> str:
        """
        Return a human-readable representation of this message.

        This should provide a detailed representation of the message, much like the body
        of an email.

        Returns:
            A human readable representation of this message.
        """
        new_line = "\n"
        return (
            f"{self.update.user.name}'s bodhi update {self.update.alias} "
            f"has reached the {self.status} karma threshold.\n"
            f"Builds:\n"
            f"{new_line.join([b.nvr for b in self.update.builds])}"
        )


class UpdateRequestMessage(UpdateMessage):
    """Sent when an update's request is changed."""

    @property
    def summary(self) -> str:
        """
        Return a short, human-readable representation of this message.

        This should provide a short summary of the message, much like the subject line
        of an email.

        Returns:
            A summary for this message.
        """
        status = self.topic.split('.')[-1]
        if status in ('unpush', 'obsolete', 'revoke'):
            return (
                f"{self.agent_name} {past_tense(status)} {self._owner_qual} update "
                f"{self.update.alias} ({self._builds_summary})"
            )
        else:
            return (
                f"{self.agent_name} submitted {self._owner_qual} update {self.update.alias} "
                f"({self._builds_summary}) to {status}"
            )

    def __str__(self) -> str:
        """
        Return a human-readable representation of this message.

        This should provide a detailed representation of the message, much like the body
        of an email.

        Returns:
            A human readable representation of this message.
        """
        status = self.topic.split('.')[-1]
        if status in ('unpush', 'obsolete', 'revoke'):
            action = past_tense(status)
        else:
            action = "submitted"
        content = [
            f"{self.agent_name} {action} {self._owner_qual} update {self.update.alias}"
        ]
        if action == "submitted":
            content.append(f" to {status}")
        content.append(".\nBuilds:\n")
        content.append("\n".join([b.nvr for b in self.update.builds]))
        return "".join(content)


class UpdateRequestRevokeV1(UpdateRequestMessage):
    """Sent when an update is revoked."""

    body_schema = {
        'id': f'{SCHEMA_URL}/v1/bodhi.update.request.revoke#',
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'description': 'Schema for message sent when an update is revoked',
        'type': 'object',
        'properties': {
            'agent': {
                'type': 'string',
                'description': 'The user who requested the update to be revoked',
            },
            'update': UpdateV1.schema(),
        },
        'required': ['agent', 'update'],
        'definitions': {
            'build': BuildV1.schema(),
        }
    }

    topic = "bodhi.update.request.revoke"


class UpdateRequestStableV1(UpdateRequestMessage):
    """Sent when an update is submitted as a stable candidate."""

    body_schema = {
        'id': f'{SCHEMA_URL}/v1/bodhi.update.request.stable#',
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'description': 'Schema for message sent when an update is requested stable',
        'type': 'object',
        'properties': {
            'agent': {
                'type': 'string',
                'description': 'The user who requested the update to be stable',
            },
            'update': UpdateV1.schema(),
        },
        'required': ['agent', 'update'],
        'definitions': {
            'build': BuildV1.schema(),
        }
    }

    topic = "bodhi.update.request.stable"


class UpdateRequestTestingV1(UpdateRequestMessage):
    """Sent when an update is submitted as a testing candidate."""

    body_schema = {
        'id': f'{SCHEMA_URL}/v1/bodhi.update.request.testing#',
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'description': 'Schema for message sent when an update is requested testing',
        'type': 'object',
        'properties': {
            'agent': {
                'type': 'string',
                'description': 'The user who requested the update to be tested',
            },
            'update': UpdateV1.schema(),
        },
        'required': ['agent', 'update'],
        'definitions': {
            'build': BuildV1.schema(),
        }
    }

    topic = "bodhi.update.request.testing"


class UpdateRequestUnpushV1(UpdateRequestMessage):
    """Sent when an update is requested to be unpushed."""

    body_schema = {
        'id': f'{SCHEMA_URL}/v1/bodhi.update.request.unpush#',
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'description': 'Schema for message sent when an update is unpushed',
        'type': 'object',
        'properties': {
            'agent': {
                'type': 'string',
                'description': 'The user who requested the update to be unpushed',
            },
            'update': UpdateV1.schema(),
        },
        'required': ['agent', 'update'],
        'definitions': {
            'build': BuildV1.schema(),
        }
    }

    topic = "bodhi.update.request.unpush"


class UpdateRequestObsoleteV1(UpdateRequestMessage):
    """Sent when an update is requested to be obsoleted."""

    body_schema = {
        'id': f'{SCHEMA_URL}/v1/bodhi.update.request.obsolete#',
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'description': 'Schema for message sent when an update is obsoleted',
        'type': 'object',
        'properties': {
            'agent': {
                'type': 'string',
                'description': 'The user who requested the update to be obsoleted',
            },
            'update': UpdateV1.schema(),
        },
        'required': ['agent', 'update'],
        'definitions': {
            'build': BuildV1.schema(),
        }
    }

    topic = "bodhi.update.request.obsolete"


class UpdateRequirementsMetStableV1(UpdateMessage):
    """Sent when all the update requirements are met for stable."""

    body_schema = {
        'id': f'{SCHEMA_URL}/v1/bodhi.update.requirements_met.stable#',
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'description': 'Schema for message sent when an update meets stable requirements',
        'type': 'object',
        'properties': {
            'update': UpdateV1.schema(),
        },
        'required': ['update'],
        'definitions': {
            'build': BuildV1.schema(),
        }
    }

    topic = "bodhi.update.requirements_met.stable"

    @property
    def summary(self) -> str:
        """
        Return a short, human-readable representation of this message.

        This should provide a short summary of the message, much like the subject line
        of an email.

        Returns:
            A summary for this message.
        """
        return (
            f"{self.update.user.name}'s {self._builds_summary} "
            f"bodhi update has met stable testing requirements"
        )

    def __str__(self) -> str:
        """
        Return a human-readable representation of this message.

        This should provide a detailed representation of the message, much like the body
        of an email.

        Returns:
            A human readable representation of this message.
        """
        new_line = "\n"
        return (
            f"{self.update.user.name}'s Bodhi update {self.update.alias}"
            f" has met stable testing requirements.\n"
            f"Builds:\n"
            f"{new_line.join([b.nvr for b in self.update.builds])}"
        )


class UpdateReadyForTestingV1(BodhiMessage):
    """
    Sent when an update is ready to be tested. Original version.

    Does not have 'update' property or inherit from UpdateMessage.
    """

    body_schema = {
        'id': f'{SCHEMA_URL}/v1/bodhi.update.status.testing#',
        '$schema': 'http://json-schema.org/draft-04/schema#',
        'description': 'Schema for message sent when an update is ready for testing',
        'type': 'object',
        'properties': {
            'contact': {
                'description': 'Schema for message sent when an update is ready for testing',
                'type': 'object',
                'properties': {
                    'name': {
                        'type': 'string',
                        'description': 'A human readable name of the team running the testing '
                        'or gating',
                    },
                    'team': {
                        'type': 'string',
                        'description': 'A human readable name of the team running the testing '
                        'or gating',
                    },
                    'docs': {
                        'type': 'string',
                        'description': ' Link to documentation with details about the system.',
                    },
                    'email': {
                        'type': 'string',
                        'description': 'Contact email address.',
                    },
                },
                'required': ['name', 'team', 'docs', 'email'],
            },
            'artifact': {
                'description': 'Details about the builds to test.',
                'type': 'object',
                'properties': {
                    'id': {
                        'description': 'The bodhi identifier for this update',
                        'type': 'string'
                    },
                    'type': {
                        'description': 'Artifact type, in this case "rpm-build-group".',
                        'type': 'string',
                    },
                    'builds': {
                        'type': 'array',
                        'description': 'A list of builds included in this group',
                        'items': {'$ref': '#/definitions/build'}
                    },
                    'repository': {
                        'description': 'Url of the repository with packages from the side-tag.',
                        'type': 'string',
                        'format': 'uri',
                    },
                    'release': {
                        'description': 'The release targetted by this side-tag/group of builds.',
                        'type': 'string',
                    },
                },
                'required': ['id', 'type', 'builds', 'repository', 'release'],
            },
            'generated_at': {
                'description': 'Time when the requested was generated, in UTC and ISO 8601 format',
                'type': 'string',
            },
            'version': {
                'description': 'Version of the specification',
                'type': 'string',
            },
            'agent': {
                'description': 'Re-trigger request: name of requester, trigger on push: "bodhi".',
                'type': 'string',
            },
        },
        'required': ['contact', 'artifact', 'generated_at', 'version', 'agent'],
        'definitions': {
            'build': {
                'description': 'Details about a build to test.',
                'type': 'object',
                'properties': {
                    'type': {
                        'description': 'Artifact type, in this case "koji-build"',
                        'type': 'string',
                    },
                    'id': {
                        'description': 'Build ID of the koji build.',
                        'type': 'integer',
                    },
                    'task_id': {
                        'description': 'Task ID of the koji build.',
                        'type': ['null', 'integer'],
                    },
                    'component': {
                        'description': 'Name of the component tested.',
                        'type': 'string',
                    },
                    'issuer': {
                        'description': 'Build issuer of the artifact.',
                        'type': 'string',
                    },
                    'scratch': {
                        'description': 'Indication if the build is a scratch build.',
                        'type': 'boolean',
                    },
                    'nvr': {
                        'description': 'Name-version-release of the artifact.',
                        'type': 'string',
                    }
                },
                'required': ['type', 'id', 'issuer', 'component', 'nvr', 'scratch'],
            }
        },
        're-trigger': {
            'type': 'bool',
            'description': 'This flag is True if the message is sent to re-trigger tests'
        }
    }

    topic = "bodhi.update.status.testing.koji-build-group.build.complete"
    severity = DEBUG

    @property
    def summary(self) -> str:
        """
        Return a short, human-readable representation of this message.

        This should provide a short summary of the message, much like the subject line
        of an email.

        Returns:
            A summary for this message.
        """
        return (
            f"{self.body['contact']['name']}'s "
            f"{truncate(' '.join([b['nvr'] for b in self.body['artifact']['builds']]))} "
            f"bodhi update is ready for testing")

    def __str__(self) -> str:
        """
        Return a human-readable representation of this message.

        This should provide a detailed representation of the message, much like the body
        of an email.

        Returns:
            A human readable representation of this message.
        """
        new_line = "\n"
        return (
            f"{self.body['contact']['name']}'s Bodhi update is ready for testing\n"
            f"Builds:\n"
            f"{new_line.join([b['nvr'] for b in self.body['artifact']['builds']])} ")

    @property
    def url(self) -> str:
        """
        Return a URL to the action that caused this message to be emitted.

        Returns:
            A relevant URL.
        """
        return f"https://bodhi.fedoraproject.org/updates/{self.body['artifact']['id']}"

    @property
    def usernames(self) -> typing.List[str]:
        """
        List of users affected by the action that generated this message.

        Returns:
            A list of affected usernames.
        """
        usernames = set([b['issuer'] for b in self.body['artifact']['builds']])
        if self.agent_name:
            usernames.add(self.agent_name)
        return sorted(usernames)

    @property
    def packages(self) -> typing.Iterable[str]:
        """
        List of names of packages affected by the action that generated this message.

        Returns:
            A list of affected package names.
        """
        packages = set([b['component'] for b in self.body['artifact']['builds']])
        return sorted(packages)

    @property
    def agent_name(self) -> typing.Union[str, None]:
        """Return the agent's username for this message.

        Returns:
            The agent's username, or None if the body has no agent key.
        """
        return self.body.get('agent', None)


class UpdateReadyForTestingV2(UpdateReadyForTestingV1):
    """
    Sent when an update is ready to be tested. Newer version.

    Has 'update' property, like other update messages.
    """

    # mypy infers that lots of the things we touch below should be
    # collections of strings and doesn't like us doing unexpected
    # things to them, so the typing.Any shuts it up
    body_schema: typing.Any = copy.deepcopy(UpdateReadyForTestingV1.body_schema)
    # we have to rename this definition as it will conflict with the
    # one expected by UpdateV1.schema()
    body_schema['definitions']['artifactbuild'] = copy.deepcopy(body_schema['definitions']['build'])
    renamed = {'$ref': '#/definitions/artifactbuild'}
    body_schema['properties']['artifact']['properties']['builds']['items'] = renamed
    body_schema['definitions']['build'] = BuildV1.schema()
    body_schema['properties']['update'] = UpdateV1.schema()
    body_schema['required'].append('update')

    @property
    def summary(self) -> str:
        """
        Return a short, human-readable representation of this message.

        This should provide a short summary of the message, much like the subject line
        of an email.

        Returns:
            A summary for this message.
        """
        return (
            f"{self.body['update']['user']['name']}'s "
            f"{truncate(' '.join([b['nvr'] for b in self.body['artifact']['builds']]))} "
            f"bodhi update is ready for testing")

    def __str__(self) -> str:
        """
        Return a human-readable representation of this message.

        This should provide a detailed representation of the message, much like the body
        of an email.

        Returns:
            A human readable representation of this message.
        """
        new_line = "\n"
        return (
            f"{self.body['update']['user']['name']}'s Bodhi update is ready for testing\n"
            f"Builds:\n"
            f"{new_line.join([b['nvr'] for b in self.body['artifact']['builds']])} ")
