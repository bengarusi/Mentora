export type Subject = "math" | "english";

export type DifficultyLevel = "easy" | "medium" | "hard";

export type LessonPhase =
  | "teaching"
  | "pre_practice_example"
  | "practice"
  | "practice_summary"
  | "summary"
  | "completed"
  | "homework_help";

export type SessionMode = "lesson" | "homework";

/** Extraction lifecycle of an uploaded file. Only "ready" material is
 * retrievable by the tutor. */
export type MaterialStatus =
  | "pending"
  | "processing"
  | "ready"
  | "unsupported"
  | "failed";

export type MaterialKind = "study_material" | "homework";

export interface StudyMaterial {
  id: number;
  student_id: number;
  session_id: number | null;
  kind: MaterialKind;
  subject: string | null;
  topic: string | null;
  subtopic: string | null;
  title: string | null;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  status: MaterialStatus;
  status_detail: string | null;
  page_count: number | null;
  chunk_count: number;
  created_at: string | null;
  processed_at: string | null;
}

export interface SupportedFormats {
  extensions: string[];
  max_upload_mb: number;
}

export interface HomeworkProgress {
  total_exercises: number;
  solved_exercises: number;
}

export interface Student {
  id: number;
  full_name: string;
  email: string;
  age: number;
  grade: string;
  math_level: string | null;
  english_level: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  student: Student;
}

export interface Session {
  id: number;
  student_id: number;
  subject: string;
  topic: string;
  subtopic: string;
  goal_text: string;
  status: string;
  phase: LessonPhase | null;
  difficulty: DifficultyLevel | null;
  mode: SessionMode;
  created_at: string | null;
  ended_at: string | null;
}

export interface Message {
  id: number;
  session_id: number;
  role: "student" | "tutor";
  content: string;
  created_at: string | null;
}

export interface TurnResult {
  tutor_message: string;
  phase: LessonPhase;
}

export interface PhaseResult {
  phase: LessonPhase;
  tutor_message: string | null;
}

export interface VoiceTurnResult {
  student_text: string;
  tutor_message: string;
  phase: LessonPhase;
  audio_base64: string | null;
}

// ---- Practice types ----

export interface PracticeQuestion {
  id: number;
  difficulty: number;
  question_text: string;
  set_number: number;
}

export interface PracticeAnswerItem {
  question_id: number;
  answer: string;
}

export interface GradedPracticeItem {
  question_id: number;
  question_text: string;
  difficulty: number;
  set_number: number;
  student_answer: string;
  is_correct: boolean;
  feedback: string;
  correct_answer: string | null;
  solution_steps: string | null;
  explanation: string | null;
}

export interface PracticeStartResult {
  set_number: number;
  questions: PracticeQuestion[];
}

export interface PracticeSubmitResult {
  set_number: number;
  grades: GradedPracticeItem[];
}

export interface PracticeSetResult {
  set_number: number;
  questions: GradedPracticeItem[];
}

export interface PracticeSummary {
  session_id: number;
  total_correct: number;
  total_questions: number;
  success_level: string | null;
  sets: PracticeSetResult[];
}

export interface LessonSummaryResponse {
  session_id: number;
  summary_text: string | null;
}

// ---- Progress / legacy types ----

export interface RecentSession {
  session_id: number;
  subject: string;
  topic: string;
  goal_text: string;
  phase: string;
  success_level: string | null;
  score: number | null;
  total_questions: number | null;
}

export interface StudentProgress {
  total_sessions: number;
  completed_sessions: number;
  sessions_by_subject: Record<string, number>;
  success_distribution: Record<string, number>;
  total_correct_answered: number;
  total_questions_answered: number;
  average_percentage: number | null;
  recent: RecentSession[];
}

// ---- topic/subtopic progress map ----
export type ProgressStatus =
  | "mastered"
  | "in_progress"
  | "needs_practice"
  | "not_started";

export interface SubtopicProgress {
  subtopic: string;
  mastery_percentage: number | null;
  status: string;
  sessions_count: number;
  last_session_id: number | null;
}

export interface TopicProgress {
  topic: string;
  mastery_percentage: number | null;
  status: string;
  sessions_count: number;
  subtopics: SubtopicProgress[];
}

export interface ProgressMap {
  topics: TopicProgress[];
}
