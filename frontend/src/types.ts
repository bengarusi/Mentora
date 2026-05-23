export type Subject = "math" | "english";

export type LessonPhase =
  | "teaching"
  | "pre_practice_example"
  | "practice"
  | "practice_summary"
  | "summary"
  | "completed";

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
