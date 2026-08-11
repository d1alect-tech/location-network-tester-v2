"""HTTP CRUD версионированных профилей."""

from fastapi import APIRouter, HTTPException, status

from lnt.errors import InputError
from lnt.profiles import (
    ConditionsProfile,
    EquipmentProfile,
    FrontEndProfile,
    LocationProfile,
    ProfileStore,
    Quantity,
    TransformerProfile,
)
from lnt.profiles.model import ProfileData, ProfileSnapshot
from lnt.ui.models_profiles import (
    ConditionsRequest,
    EquipmentRequest,
    FrontEndRequest,
    LocationRequest,
    ProfileListResponse,
    ProfileRequest,
    ProfileResponse,
    TransformerRequest,
)

router = APIRouter(prefix="/api/profiles")


def _data(request: ProfileRequest) -> ProfileData:
    match request:
        case LocationRequest(data=data):
            return LocationProfile(**data.model_dump())
        case EquipmentRequest(data=data):
            return EquipmentProfile(**data.model_dump())
        case FrontEndRequest(data=data):
            return FrontEndProfile(
                resistance=Quantity(**data.resistance.model_dump()),
                c1=Quantity(**data.c1.model_dump()),
                c2=Quantity(**data.c2.model_dump()),
            )
        case TransformerRequest(data=data):
            return TransformerProfile(
                nominal_primary=Quantity(**data.nominal_primary.model_dump()),
                nominal_secondary=Quantity(**data.nominal_secondary.model_dump()),
            )
        case ConditionsRequest(data=data):
            return ConditionsProfile(
                damper_state=data.damper_state,
                nearby_load_states=data.nearby_load_states,
            )


def _response(snapshot: ProfileSnapshot) -> ProfileResponse:
    return ProfileResponse.model_validate(snapshot, from_attributes=True)


def _store() -> ProfileStore:
    return ProfileStore()


def _mapped(error: InputError, *, conflict: bool = False) -> HTTPException:
    message = str(error)
    if conflict:
        return HTTPException(status.HTTP_409_CONFLICT, message)
    if "не найден" in message or "удалён" in message:
        return HTTPException(status.HTTP_404_NOT_FOUND, message)
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


@router.get("")
def list_profiles() -> ProfileListResponse:
    """Перечисляет последние активные revisions."""
    return ProfileListResponse(items=tuple(_response(item) for item in _store().list()))


@router.get("/{profile_id}")
def show_profile(profile_id: str) -> ProfileResponse:
    """Возвращает последнюю активную revision."""
    try:
        return _response(_store().get(profile_id))
    except InputError as error:
        raise _mapped(error) from error


@router.get("/{profile_id}/history")
def profile_history(profile_id: str) -> ProfileListResponse:
    """Возвращает неизменяемую историю профиля."""
    try:
        history = _store().history(profile_id)
    except InputError as error:
        raise _mapped(error) from error
    if not history:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "профиль не найден")
    return ProfileListResponse(items=tuple(_response(item) for item in history))


@router.post("/{profile_id}", status_code=status.HTTP_201_CREATED)
def create_profile(profile_id: str, request: ProfileRequest) -> ProfileResponse:
    """Создаёт первую revision нового профиля."""
    try:
        return _response(_store().create(profile_id, _data(request)))
    except InputError as error:
        raise _mapped(error, conflict="уже существует" in str(error)) from error


@router.put("/{profile_id}")
def update_profile(profile_id: str, request: ProfileRequest) -> ProfileResponse:
    """Добавляет revision существующего профиля."""
    try:
        return _response(_store().update(profile_id, _data(request)))
    except InputError as error:
        raise _mapped(error) from error


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: str) -> None:
    """Скрывает профиль marker-файлом, сохраняя историю."""
    try:
        _store().delete(profile_id)
    except InputError as error:
        raise _mapped(error) from error
