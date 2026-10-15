"""사용자에게 그대로 보여줄 수 있는 오류 타입들."""


class ChessCoachError(Exception):
    """chess-coach의 모든 예상 가능한 오류의 부모 클래스."""


class EngineNotFoundError(ChessCoachError):
    """Stockfish 실행 파일을 찾지 못함."""


class FetchError(ChessCoachError):
    """chess.com 게임 가져오기 실패."""


class LLMError(ChessCoachError):
    """로컬 LLM(Ollama) 호출 실패."""


class KnowledgeError(ChessCoachError):
    """지식 베이스(노트/책 조각) 로딩 실패."""


class IngestError(ChessCoachError):
    """책 파일을 지식 베이스로 가져오는 데 실패."""
