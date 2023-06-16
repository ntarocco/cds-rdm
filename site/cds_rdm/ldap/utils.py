# -*- coding: utf-8 -*-
#
# Copyright (C) 2023 CERN.
#
# CDS-RDM is free software; you can redistribute it and/or modify it under
# the terms of the MIT License; see LICENSE file for more details.

"""CDS-RDM ldap serializers."""

from functools import partial

from cds_rdm.ldap.errors import InvalidLdapUser
from invenio_accounts.models import User
from invenio_oauthclient.models import UserIdentity
from invenio_userprofiles import UserProfile


def serialize_ldap_user(ldap_user_data, log_func=None):
    """Create ldap user."""

    def serialize(ldap_user_data):
        decoded_data = {}
        for key, value in ldap_user_data.items():
            # get first value of each field from LDAP
            # decode bytes to UTF-8
            decoded_data[key] = value[0].decode("utf8")
        serialized_data = dict(
            user_email=decoded_data["mail"].lower(),
            user_profile_full_name=decoded_data["displayName"],
            user_identity_id=decoded_data["uidNumber"],
            cern_account_type=decoded_data["cernAccountType"],
            remote_account_person_id=str(decoded_data["employeeID"]),
            remote_account_department=decoded_data["department"],
        )

        return serialized_data

    def validate_required(ldap_user_data, employee_id, log_func):
        if "mail" not in ldap_user_data:
            log_func_missing_email = partial(
                log_func, extra=dict(employee_id=employee_id)
            )
            raise InvalidLdapUser(
                f"LDAP user with employeeID {employee_id}" f"has no email address.",
                log_func=log_func_missing_email,
            )

    def validate_user_data(serialized_ldap_user_data, employee_id, log_func):
        """Validate user data values."""
        email = serialized_ldap_user_data["user_email"]
        # check if email is empty string.
        # It happens when the account is not fully created on LDAP
        if not email:
            log_func_missing_email = partial(
                log_func, extra=dict(employee_id=employee_id)
            )
            raise InvalidLdapUser(
                f"LDAP user with employeeID {employee_id}" f" has no email address.",
                log_func=log_func_missing_email,
            )

    employee_id = ldap_user_data["employeeID"][0].decode("utf8")
    try:
        validate_required(ldap_user_data, employee_id, log_func)
        serialized_data = serialize(ldap_user_data)
        validate_user_data(serialized_data, employee_id, log_func)
        return serialized_data
    except InvalidLdapUser:
        return


def user_exists(ldap_user):
    """Check if user exists in the db."""
    if not ldap_user:
        return False

    email = ldap_user["user_email"]
    user_email_exists = User.query.filter_by(email=email).count() > 0

    if user_email_exists:
        return True

    user_identity_exists = (
        UserIdentity.query.filter_by(id_user=ldap_user["user_identity_id"]).count() > 0
    )
    if user_identity_exists:
        return True


class InvenioUser:
    """Invenio user serializer class."""

    def __init__(self, remote_account):
        """Constructor."""
        self.user_id = remote_account.user_id
        self.remote_account = remote_account
        self.user_profile = UserProfile.get_by_userid(self.user_id)
        self.user_identity = UserIdentity.query.filter_by(id_user=self.user_id).one()
        self.user = User.query.filter_by(id=self.user_id).one()
        self.data = self._get_full_user_info()

    def _get_full_user_info(self):
        """Serialize data from user db models."""
        user_info = dict(
            user_profile_full_name=self.user_profile.full_name,
            user_email=self.user.email,
            user_identity_id=self.user_identity.id,
            remote_account_id=self.remote_account.id,
            remote_account_person_id=str(self.remote_account.extra_data["person_id"]),
            remote_account_department=self.remote_account.extra_data.get("department"),
        )
        return user_info

    def update(self, ldap_user):
        """Update invenio user with ldap data."""
        ra = self.remote_account
        ra.extra_data["department"] = ldap_user["remote_account_department"]
        self.user.email = ldap_user["user_email"]
        self.user_profile.full_name = ldap_user["user_profile_full_name"]
