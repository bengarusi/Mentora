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

export type StreamEvent =
  | { type: "stream_start" }
  | { type: "text_delta"; data: string }
  | { type: "tool_start"; tool_name: string; status?: string }
  | { type: "tool_end"; tool_name: string; status?: string }
  | { type: "audio_start"; chunk_id: number }
  | { type: "audio_delta"; chunk_id: number; data: string }
  | { type: "audio_end"; chunk_id: number }
  | { type: "done" }
  | { type: "error"; message: string };

export interface ToolActivity {
  id: number;
  toolName: string;
  status: "running" | "complete" | "error";
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

// ---- Visual board explanations ----
// Mirrors app/schemas/board.py. The model supplies parameters (slope, numerator,
// dimensions) and the renderer computes the geometry, so a drawing can never
// disagree with the numbers it was built from.

/** Where a board came from. There is deliberately no board while a student is
 * still answering a practice question — that is theirs to work through. */
export type BoardKind = "lesson_intro" | "chat" | "practice_review";

export interface BoardStepItem {
  math: string; // LaTeX without $ delimiters
  operation: string | null;
  note: string | null;
  emphasis: "none" | "highlight" | "underline" | "circle" | "strike";
  emphasis_tone: "neutral" | "good" | "bad";
}

interface BoardBlockBase {
  id: string;
  caption: string; // also the SVG <title> / accessible description
  /** What the tutor says while this block is written. Drives both the spoken
   * narration and the caption bar. */
  narration: string;
}

export interface BoardStepsBlock extends BoardBlockBase {
  kind: "steps";
  items: BoardStepItem[];
}

export interface BoardCalloutBlock extends BoardBlockBase {
  kind: "callout";
  tone: "insight" | "warning" | "common_mistake";
  text: string;
}

export interface BoardExpressionCompareBlock extends BoardBlockBase {
  kind: "expression_compare";
  left: string;
  right: string;
  relation: "<" | ">" | "=" | "≈";
  left_label: string | null;
  right_label: string | null;
  rewrite_left: string | null;
  rewrite_right: string | null;
}

export interface BoardFractionBar {
  numerator: number;
  denominator: number;
  label: string | null;
}

export interface BoardFractionBarsBlock extends BoardBlockBase {
  kind: "fraction_bars";
  bars: BoardFractionBar[];
}

export interface BoardNumberLinePoint {
  value: number;
  label: string | null;
  style: "dot" | "open" | "filled";
}

export interface BoardNumberLineBlock extends BoardBlockBase {
  kind: "number_line";
  min: number;
  max: number;
  tick: number;
  points: BoardNumberLinePoint[];
  interval: {
    start: number | null;
    end: number | null;
    inclusive_start: boolean;
    inclusive_end: boolean;
  } | null;
}

export interface BoardCoordinatePlaneBlock extends BoardBlockBase {
  kind: "coordinate_plane";
  x_min: number;
  x_max: number;
  y_min: number;
  y_max: number;
  lines: { slope: number; intercept: number; label: string | null }[];
  points: { x: number; y: number; label: string | null }[];
  slope_triangle: number | null;
}

export interface BoardGeometryFigureBlock extends BoardBlockBase {
  kind: "geometry_figure";
  shape: "triangle" | "rectangle" | "circle";
  dimensions: Record<string, number>;
  labels: { target: string; text: string }[];
  right_angle_at: string | null;
}

export type BoardBlock =
  | BoardStepsBlock
  | BoardCalloutBlock
  | BoardExpressionCompareBlock
  | BoardFractionBarsBlock
  | BoardNumberLineBlock
  | BoardCoordinatePlaneBlock
  | BoardGeometryFigureBlock;

export interface BoardSpec {
  title: string;
  intro: string;
  blocks: BoardBlock[];
  final_answer: string | null;
}

export interface BoardSummary {
  id: number;
  kind: BoardKind;
  /** Exactly one of these is set, depending on kind. */
  message_id: number | null;
  question_id: number | null;
  title: string;
  created_at: string | null;
}

export interface BoardListResponse {
  /** False when the feature flag is off — the frontend has no flag system, so
   * the capability arrives as data and the action simply isn't rendered. */
  enabled: boolean;
  boards: BoardSummary[];
}

export interface BoardResponse {
  id: number;
  kind: BoardKind;
  message_id: number | null;
  question_id: number | null;
  spec: BoardSpec;
  created_at: string | null;
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
