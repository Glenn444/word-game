from fastapi import FastAPI, Depends, HTTPException, Cookie, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool
import random
import string
from datetime import datetime
import uuid
import jwt
from datetime import datetime, timedelta
import json
from config import Config

# Configuration
DB_CONFIG = {
        "dbname": Config.DBNAME,
        "user": Config.DBSER,  # Change as needed
        "password": Config.DBPASSWORD,  # Change as needed
        "host": Config.DBHOST,
        "sslmode":"require"
    }
SECRET_KEY = Config.SECRET_KEY  # Change this in production!
ALGORITHM = Config.ALGORITHM
SESSION_COOKIE_NAME = Config.SESSION_COOKIE_NAME
SESSION_EXPIRY_DAYS = Config.SESSION_EXPIRY_DAYS

# Create a connection pool
conn_pool = SimpleConnectionPool(1, 10, **DB_CONFIG)

# Create FastAPI app
app = FastAPI(title="Word Bridge Game API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Modify in production to limit to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Database Helpers ---

def get_db_connection():
    """Get a connection from the pool"""
    conn = conn_pool.getconn()
    try:
        yield conn
    finally:
        conn_pool.putconn(conn)

# --- Session Management ---

def generate_username():
    """Generate a random fun username for new users"""
    adjectives = ["Happy", "Lucky", "Brave", "Clever", "Mighty", "Swift", "Wise", "Agile", "Bold", "Wild"]
    animals = ["Tiger", "Eagle", "Dolphin", "Fox", "Panda", "Wolf", "Bear", "Lion", "Hawk", "Shark"]
    
    return f"{random.choice(adjectives)}{random.choice(animals)}{random.randint(1, 999)}"

def create_session_token(user_id, username):
    """Create a JWT session token"""
    expiry = datetime.now() + timedelta(days=SESSION_EXPIRY_DAYS)
    payload = {
        "sub": str(user_id),
        "username": username,
        "score": 0,
        "exp": expiry,
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token

def get_session_data(session_token: str = Cookie(None, alias=SESSION_COOKIE_NAME)):
    """Decode and validate session token"""
    
    if not session_token:
      
        return None
    
    try:
      
        payload = jwt.decode(jwt=session_token, key=SECRET_KEY, algorithms=[ALGORITHM])
        # Check if session has expired
        if datetime.fromtimestamp(payload["exp"]) < datetime.now():
       
            return None
            
        return payload
        
    except jwt.PyJWTError as e:
        
        return None

def update_session_score(session_data, new_score):
    """Update session with new score and return new token"""
    if not session_data:
        return None
        
    # Keep existing fields but update score
    session_data["score"] = new_score
    
    # Update iat but keep same expiration
    #session_data["iat"] = datetime.now()
    
    # Generate new token
    token = jwt.encode(session_data, SECRET_KEY, algorithm=ALGORITHM)
    return token

# --- Models ---

class GameOptions(BaseModel):
    """Options for game configuration"""
    category_id: Optional[int] = None

class GameSession(BaseModel):
    """Session information"""
    user_id: str
    username: str
    score: int

class WordPair(BaseModel):
    """A start-end word pair"""
    id: int
    start_word: str
    end_word: str

class GameStep(BaseModel):
    """A single step in the game"""
    position: int
    correct_word: str
    options: List[str]

class GameData(BaseModel):
    """Game data for a word pair"""
    pair_id: int
    start_word: str
    end_word: str
    steps: List[GameStep]

class GuessRequest(BaseModel):
    """A guess request from the player"""
    pair_id: int
    position: int
    word: str

class GuessResponse(BaseModel):
    """Response to a guess"""
    correct: bool
    correct_word: str
    next_position: Optional[int] = None
    game_completed: bool = False
    new_score: int = 0

# --- Routes ---

@app.get("/")
def read_root():
    """API root - basic info"""
    return {"message": "Word Bridge Game API", "version": "0.1.0"}

@app.post("/session", response_model=GameSession)
def create_or_get_session(response: Response):
    """Create a new session or return existing session"""
    # Generate a new user ID and username
    user_id = str(uuid.uuid4())
    username = generate_username()
    
    # Create session token
    token = create_session_token(user_id, username)
    
    # Set the cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=SESSION_EXPIRY_DAYS * 24 * 60 * 60,
        samesite="lax"
    )
    
    return GameSession(user_id=user_id, username=username, score=0)

@app.get("/session", response_model=Optional[GameSession])
def get_session(session_data: dict = Depends(get_session_data)):
    """Get current session information"""
    if not session_data:
        raise HTTPException(status_code=401, detail="No active session")
    
    return GameSession(
        user_id=session_data["sub"],
        username=session_data["username"],
        score=session_data["score"]
    )

@app.post("/game", response_model=GameData)
def start_game(
    options: GameOptions,
    conn = Depends(get_db_connection),
    session_data: dict = Depends(get_session_data)
):
    """Start a new game by getting a random word pair and associated steps"""
    if not session_data:
        raise HTTPException(status_code=401, detail="No active session")
    
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Get a random word pair, optionally filtered by category
        if options.category_id:
            cursor.execute(
                "SELECT id, start_word, end_word FROM word_pairs WHERE category_id = %s ORDER BY RANDOM() LIMIT 1",
                (options.category_id,)
            )
        else:
            cursor.execute(
                "SELECT id, start_word, end_word FROM word_pairs ORDER BY RANDOM() LIMIT 1"
            )
        
        pair = cursor.fetchone()
        if not pair:
            raise HTTPException(status_code=404, detail="No word pairs found")
        
        pair_id = pair["id"]
        
        # Get all bridge words with their positions and distractors
        cursor.execute("""
            SELECT 
                bw.position, 
                bw.word AS correct_word,
                ARRAY_AGG(d.word) AS distractors
            FROM 
                bridge_words bw
            LEFT JOIN 
                distractors d ON bw.id = d.bridge_word_id
            WHERE 
                bw.word_pair_id = %s
            GROUP BY 
                bw.id, bw.position, bw.word
            ORDER BY 
                bw.position
        """, (pair_id,))
        
        steps = []
        for row in cursor.fetchall():
            position = row["position"]
            correct_word = row["correct_word"]
            distractors = [d for d in row["distractors"] if d]  # Filter out any None values
            
            # Create a list of all options (correct word + distractors)
            all_words = [correct_word] + distractors
            
            # Shuffle the words to randomize their order
            random.shuffle(all_words)
            
            steps.append(GameStep(
                position=position,
                correct_word=correct_word,
                options=all_words
            ))
        
        return GameData(
            pair_id=pair_id,
            start_word=pair["start_word"],
            end_word=pair["end_word"],
            steps=steps
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cursor.close()

@app.post("/guess", response_model=GuessResponse)
def make_guess(
    guess: GuessRequest,
    response: Response,
    conn = Depends(get_db_connection),
    session_data: dict = Depends(get_session_data)
):
    """Make a guess for a specific position in a word sequence"""
    if not session_data:
        raise HTTPException(status_code=401, detail="No active session")
    
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Verify the word pair exists
        cursor.execute(
            "SELECT id FROM word_pairs WHERE id = %s",
            (guess.pair_id,)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Word pair not found")
        
        # Get the correct bridge word for this position
        cursor.execute("""
            SELECT word FROM bridge_words 
            WHERE word_pair_id = %s AND position = %s
        """, (guess.pair_id, guess.position))
        
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Bridge word position not found")
        
        correct_word = result["word"]
        is_correct = (guess.word == correct_word)
        
        # Check if this was the last position
        is_last_position = (guess.position == 3)  # Assuming 3 steps
        game_completed = is_correct and is_last_position
        
        # Calculate new score
        current_score = session_data.get("score", 0)
        new_score = current_score
        
        if is_correct:
            # Add points for correct guess
            new_score += 10
            
            # Bonus points for completing the game
            if game_completed:
                new_score += 20
        else:
            new_score -= 5
        
        # Get next position if not completed
        next_position = None
        if is_correct and not is_last_position:
            next_position = guess.position + 1
        
        # Update session with new score
        updated_token = update_session_score(session_data, new_score)
        
        if updated_token:
            # Set updated session cookie
            response.set_cookie(
                key=SESSION_COOKIE_NAME,
                value=updated_token,
                httponly=True,
                max_age=SESSION_EXPIRY_DAYS * 24 * 60 * 60,
                samesite="lax"
            )
        
        return GuessResponse(
            correct=is_correct,
            correct_word=correct_word,
            next_position=next_position,
            game_completed=game_completed,
            new_score=new_score
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cursor.close()

@app.post("/restart", response_model=GameData)
def restart_game(
    options: GameOptions,
    response: Response,
    conn = Depends(get_db_connection),
    session_data: dict = Depends(get_session_data)
):
    """
    Restart the game by resetting score to zero and fetching a new game.
    Keeps the same user ID and username.
    """
    if not session_data:
        raise HTTPException(status_code=401, detail="No active session")
    
    # Keep the same user_id and username, but reset score to zero
    user_id = session_data["sub"]
    username = session_data["username"]
    
    # Create a new session token with score reset to zero
    expiry = datetime.fromtimestamp(session_data["exp"])
    payload = {
        "sub": user_id,
        "username": username,
        "score": 0,
        "exp": expiry,
        "iat": datetime.now()
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    # Update the cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=SESSION_EXPIRY_DAYS * 24 * 60 * 60,
        samesite="lax"
    )
    
    # Fetch a new game
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Get a random word pair, optionally filtered by category
        if options.category_id:
            cursor.execute(
                "SELECT id, start_word, end_word FROM word_pairs WHERE category_id = %s ORDER BY RANDOM() LIMIT 1",
                (options.category_id,)
            )
        else:
            cursor.execute(
                "SELECT id, start_word, end_word FROM word_pairs ORDER BY RANDOM() LIMIT 1"
            )
        
        pair = cursor.fetchone()
        if not pair:
            raise HTTPException(status_code=404, detail="No word pairs found")
        
        pair_id = pair["id"]
        
        # Get all bridge words with their positions and distractors
        cursor.execute("""
            SELECT 
                bw.position, 
                bw.word AS correct_word,
                ARRAY_AGG(d.word) AS distractors
            FROM 
                bridge_words bw
            LEFT JOIN 
                distractors d ON bw.id = d.bridge_word_id
            WHERE 
                bw.word_pair_id = %s
            GROUP BY 
                bw.id, bw.position, bw.word
            ORDER BY 
                bw.position
        """, (pair_id,))
        
        steps = []
        for row in cursor.fetchall():
            position = row["position"]
            correct_word = row["correct_word"]
            distractors = [d for d in row["distractors"] if d]  # Filter out any None values
            
            # Create a list of all options (correct word + distractors)
            all_words = [correct_word] + distractors
            
            # Shuffle the words to randomize their order
            random.shuffle(all_words)
            
            steps.append(GameStep(
                position=position,
                correct_word=correct_word,
                options=all_words
            ))
        
        return GameData(
            pair_id=pair_id,
            start_word=pair["start_word"],
            end_word=pair["end_word"],
            steps=steps
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        cursor.close()



# For local testing
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)