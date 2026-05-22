export type Subject = "math" | "english";

export type LessonPhase =
  | "explanation"
  | "example"
  | "assessment"
  | "correction"
  | "level_adjustment"
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

export interface Question {
  id: number;
  difficulty: number;
  question_text: string;
}

export interface GradedAnswer {
  question_id: number;
  is_correct: boolean;
  feedback: string;
  remaining: number;
}

export interface QuestionResult {
  id: number;
  difficulty: number;
  question_text: string;
  student_answer: string | null;
  is_correct: boolean | null;
  feedback: string | null;
}

export interface SessionSummary {
  session_id: number;
  success_level: string | null;
  score: number | null;
  summary_text: string | null;
  questions: QuestionResult[];
}

export interface RecentSession {
  session_id: number;
  subject: string;
  topic: string;
  goal_text: string;
  phase: string;
  success_level: string | null;
  score: number | null;
}

export interface StudentProgress {
  total_sessions: number;
  completed_sessions: number;
  sessions_by_subject: Record<string, number>;
  success_distribution: Record<string, number>;
  average_score: number | null;
  recent: RecentSession[];
}
