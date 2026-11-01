"""forge.identity - Coherent synthetic identity generation."""
from forge.identity.generator import (
    SyntheticIdentity,
    display_name,
    full_name,
    generate_dob,
    make_fullz,
    password,
    username,
)
from forge.identity.geo import COUNTRIES, COUNTRY_LABEL, GEO, NAMES

__all__ = [
    "COUNTRIES",
    "COUNTRY_LABEL",
    "GEO",
    "NAMES",
    "SyntheticIdentity",
    "display_name",
    "full_name",
    "generate_dob",
    "make_fullz",
    "password",
    "username",
]
