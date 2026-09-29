from fastapi import APIRouter, Depends
from api.errors import or_404
from api.schemas import CharacterCreate, CharacterResponse
from util.crud.character import get_character, get_all_characters, create_character
from util.db_util import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/characters", tags=["characters"])

# Depends -> python的依賴注入(@Autowired) 傳方法名


@router.post("/")
def create(character_create: CharacterCreate, db: Session = Depends(get_db)):
    character_name = character_create.name

    character = create_character(db, character_name)

    return CharacterResponse.model_validate(character)


# 多筆交給FastAPI處理(response_model)
@router.get("/", response_model=list[CharacterResponse])
def get_all(db: Session = Depends(get_db)):
    characters = get_all_characters(db)
    return characters


@router.get("/{character_id}")
def get_one_by_id(character_id: int, db: Session = Depends(get_db)):

    character = or_404(get_character(db, character_id), "Character", character_id)
    return CharacterResponse.model_validate(character)
