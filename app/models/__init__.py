"""
Models package for PPSC Paper Bank application.
"""

from .base import TimestampMixin, BaseModel
from .category import (
    Category, 
    CategoryCreate, 
    CategoryUpdate, 
    CategoryResponse,
    CategoryService,
    CategoryDetailResponse,
    CategorySlugManager,
    create_slug
)
from .mcqs_bank import (
    MCQ, MCQBase, MCQCreate, MCQUpdate, MCQBulkCreate, MCQRead, AnswerOption
)
from .paper import PaperModel, PaperMCQ, PaperCreate, PaperUpdate, PaperResponse
from .website import Website, WebsiteCreate, WebsiteUpdate, WebsiteRead
from .scraping_state import ScrapingState, ScrapingStatus
from .websites import Websites, WebsitesCreate, WebsitesUpdate, WebsitesRead
from .top_bar import TopBar, TopBarCreate, TopBarUpdate, TopBarRead
from .side_bar import SideBar, SideBarCreate, SideBarUpdate, SideBarRead
from .interview import (
    InterviewSession,
    InterviewMessage,
    InterviewFeedback,
    InterviewQuestionScore,
    InterviewSessionRead,
    InterviewMessageRead,
    InterviewFeedbackRead,
    InterviewQuestionScoreRead,
    InterviewSessionDetail,
    InterviewMode,
    MessageRole,
    SessionStatus,
)
from .user import User, UserSession, UserRole, OAuthProvider, UserRegister, UserLogin, UserRead, UserUpdate, TokenResponse
from .community import (
    MCQFavorite, MCQFavoriteCreate, MCQFavoriteRead,
    MCQDiscussion, MCQDiscussionCreate, MCQDiscussionRead,
    MCQSubmission, MCQSubmissionCreate, MCQStatsRead,
    MCQTranslation, MCQTranslationCreate, MCQTranslationRead,
)
from .session import (
    MockSession, MockSessionCreate, MockSessionRead, MockSessionStatus,
    MockSessionAnswer, MockSessionAnswerCreate,
    DailyPaper, DailyPaperRead,
    DailyPaperAttempt, DailyPaperAttemptRead,
)
from .learning import (
    LearningGoal, LearningGoalCreate, LearningGoalRead, GoalStatus,
    LearningActivity, LearningActivityRead, ActivityType,
    StudyStreak, StudyStreakRead,
)
from .suggestion import (
    UserSuggestion, SuggestionCreate, SuggestionRead, SuggestionAdminUpdate,
    SuggestionUpvote, SuggestionCategory, SuggestionStatus,
)
from .paper_series import (
    PaperSeries,
    PaperSeriesDay,
    PaperSeriesAttempt,
    PaperSeriesRewardLog,
    PaperSeriesMode,
    PaperSeriesStatus,
    PaperSeriesPhase,
    PaperSeriesCreate,
    PaperSeriesRead,
    PaperSeriesDayRead,
    PaperSeriesAttemptStartResponse,
    PaperSeriesAttemptSubmit,
    PaperSeriesRewardRead,
)
from .vocab import (
    Word,
    DayPlan,
    UserVocabSettings,
    VocabCustomTheme,
    VocabDailyProgress,
    WordCreate,
    WordRead,
    DayPlanCreate,
    DayPlanRead,
    UserVocabSettingsUpdate,
    UserVocabSettingsRead,
    VocabCustomThemeCreate,
    VocabCustomThemeRead,
    VocabDailyProgressSync,
    VocabDailyProgressRead,
    VocabAiExplanation,
    VocabAiExplanationCreate,
    VocabAiExplanationRead,
    VocabQuizResult,
    VocabQuizResultCreate,
    VocabQuizResultRead,
    BOX_INTERVAL_DAYS,
    BOX_LEVEL_LABELS,
    VOCAB_METHODS,
    BUILTIN_CARD_THEMES,
)
from .subject_notes import (
    SubjectPreparationNote,
    SubjectPreparationNoteCreate,
    SubjectPreparationNoteUpdate,
    SubjectPreparationNoteRead,
)
from .news import (
    NewsArticle,
    NewsMCQ,
    NewsVocab,
    NewsPoVAnalysis,
    NewsArticleRead,
    NewsMCQRead,
    NewsVocabRead,
    NewsPoVAnalysisRead,
    NewsCollectionRequest,
    NewsCollectionResponse,
    NewsVocabImportRequest,
    NewsAgentChatRequest,
)


__all__ = [
    # Base models
    "TimestampMixin",
    "BaseModel",
    
    # Enums
    "AnswerOption",
    
    # Category models
    "Category",
    "CategoryCreate",
    "CategoryUpdate", 
    "CategoryResponse",
    "CategoryService",
    "CategoryDetailResponse",
    "CategorySlugManager",
    "create_slug",
    
    # MCQ models
    "MCQ",
    "MCQBase", 
    "MCQCreate",
    "MCQUpdate",
    "MCQBulkCreate",
    "MCQRead",
    
    # Paper models
    "PaperModel",
    "PaperMCQ", 
    "PaperCreate",
    "PaperUpdate",
    "PaperResponse",
    
    # Website models
    "Website",
    "WebsiteCreate",
    "WebsiteUpdate",
    "WebsiteRead",
    
    # Websites models
    "Websites",
    "WebsitesCreate", 
    "WebsitesUpdate",
    "WebsitesRead",
    
    # Navigation models
    "TopBar",
    "TopBarCreate",
    "TopBarUpdate",
    "TopBarRead",
    "SideBar", 
    "SideBarCreate",
    "SideBarUpdate",
    "SideBarRead",

    # Interview models
    "InterviewSession",
    "InterviewMessage",
    "InterviewFeedback",
    "InterviewQuestionScore",
    "InterviewSessionRead",
    "InterviewMessageRead",
    "InterviewFeedbackRead",
    "InterviewQuestionScoreRead",
    "InterviewSessionDetail",
    "InterviewMode",
    "MessageRole",
    "SessionStatus",

    # Vocab models
    "Word",
    "DayPlan",
    "UserVocabSettings",
    "VocabCustomTheme",
    "VocabDailyProgress",
    "WordCreate",
    "WordRead",
    "DayPlanCreate",
    "DayPlanRead",
    "UserVocabSettingsUpdate",
    "UserVocabSettingsRead",
    "VocabCustomThemeCreate",
    "VocabCustomThemeRead",
    "VocabDailyProgressSync",
    "VocabDailyProgressRead",
    "VocabAiExplanation",
    "VocabAiExplanationCreate",
    "VocabAiExplanationRead",
    "VocabQuizResult",
    "VocabQuizResultCreate",
    "VocabQuizResultRead",
    "BOX_INTERVAL_DAYS",
    "BOX_LEVEL_LABELS",
    "VOCAB_METHODS",
    "BUILTIN_CARD_THEMES",

    # Subject preparation notes
    "SubjectPreparationNote",
    "SubjectPreparationNoteCreate",
    "SubjectPreparationNoteUpdate",
    "SubjectPreparationNoteRead",

    # News & Current Affairs models
    "NewsArticle",
    "NewsMCQ",
    "NewsVocab",
    "NewsPoVAnalysis",
    "NewsArticleRead",
    "NewsMCQRead",
    "NewsVocabRead",
    "NewsPoVAnalysisRead",
    "NewsCollectionRequest",
    "NewsCollectionResponse",
    "NewsVocabImportRequest",
    "NewsAgentChatRequest",
]
