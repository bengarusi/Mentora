export type Difficulty = "easy" | "medium" | "hard";

export interface Subtopic {
  id: string;
  title: string;
  description: string;
  goal_text: string;
  difficulty?: Difficulty;
}

export interface MathTopic {
  id: string;
  title: string;
  description: string;
  /** Material Symbols Outlined icon name */
  icon: string;
  subtopics: Subtopic[];
}

export const MATH_CURRICULUM: MathTopic[] = [
  {
    id: "numbers-place-value",
    title: "Numbers & Place Value",
    description: "Read, write, and understand what each digit is worth.",
    icon: "tag",
    subtopics: [
      {
        id: "reading-writing-numbers",
        title: "Reading and writing numbers",
        description: "Say and write numbers up to the thousands.",
        goal_text: "I want to read and write numbers correctly up to the thousands.",
        difficulty: "easy",
      },
      {
        id: "place-value",
        title: "Place value",
        description: "Know the value of each digit in a number.",
        goal_text: "I want to understand the place value of each digit in a number.",
        difficulty: "easy",
      },
      {
        id: "comparing-numbers",
        title: "Comparing numbers",
        description: "Use greater than, less than, and equal to.",
        goal_text: "I want to compare numbers using <, >, and =.",
        difficulty: "medium",
      },
      {
        id: "rounding-numbers",
        title: "Rounding numbers",
        description: "Round numbers to the nearest ten or hundred.",
        goal_text: "I want to round numbers to the nearest ten and hundred.",
        difficulty: "medium",
      },
    ],
  },
  {
    id: "addition-subtraction",
    title: "Addition & Subtraction",
    description: "Add and take away numbers, big and small.",
    icon: "add",
    subtopics: [
      {
        id: "addition-basics",
        title: "Addition basics",
        description: "Add numbers together step by step.",
        goal_text: "I want to confidently add numbers together.",
        difficulty: "easy",
      },
      {
        id: "subtraction-basics",
        title: "Subtraction basics",
        description: "Take one number away from another.",
        goal_text: "I want to confidently subtract one number from another.",
        difficulty: "easy",
      },
      {
        id: "carrying-borrowing",
        title: "Carrying and borrowing",
        description: "Regroup when adding or subtracting larger numbers.",
        goal_text: "I want to add and subtract using carrying and borrowing.",
        difficulty: "medium",
      },
      {
        id: "add-sub-word-problems",
        title: "Word problems",
        description: "Solve real-life add and subtract stories.",
        goal_text: "I want to solve word problems using addition and subtraction.",
        difficulty: "hard",
      },
    ],
  },
  {
    id: "multiplication-division",
    title: "Multiplication & Division",
    description: "Group, share, and use the times tables.",
    icon: "calculate",
    subtopics: [
      {
        id: "multiplication-basics",
        title: "Multiplication basics",
        description: "See multiplication as repeated addition.",
        goal_text: "I want to understand and do basic multiplication.",
        difficulty: "easy",
      },
      {
        id: "division-basics",
        title: "Division basics",
        description: "Share a number into equal groups.",
        goal_text: "I want to understand and do basic division.",
        difficulty: "medium",
      },
      {
        id: "times-tables",
        title: "Times tables",
        description: "Practice and remember the times tables.",
        goal_text: "I want to know my times tables by heart.",
        difficulty: "medium",
      },
      {
        id: "mul-div-word-problems",
        title: "Multiplication and division word problems",
        description: "Solve stories using multiplying and dividing.",
        goal_text: "I want to solve word problems using multiplication and division.",
        difficulty: "hard",
      },
    ],
  },
  {
    id: "fractions",
    title: "Fractions",
    description: "Understand parts of a whole.",
    icon: "pie_chart",
    subtopics: [
      {
        id: "what-is-a-fraction",
        title: "What is a fraction?",
        description: "Learn numerators, denominators, and parts of a whole.",
        goal_text: "I want to understand what a fraction means.",
        difficulty: "easy",
      },
      {
        id: "equivalent-fractions",
        title: "Equivalent fractions",
        description: "Find fractions that are equal in value.",
        goal_text: "I want to find and recognize equivalent fractions.",
        difficulty: "medium",
      },
      {
        id: "adding-fractions",
        title: "Adding fractions",
        description: "Add fractions together.",
        goal_text: "I want to add fractions correctly.",
        difficulty: "hard",
      },
      {
        id: "comparing-fractions",
        title: "Comparing fractions",
        description: "Decide which fraction is bigger or smaller.",
        goal_text: "I want to compare fractions and know which is larger.",
        difficulty: "medium",
      },
    ],
  },
  {
    id: "decimals-percentages",
    title: "Decimals & Percentages",
    description: "Work with decimals and percents.",
    icon: "percent",
    subtopics: [
      {
        id: "decimal-place-value",
        title: "Decimal place value",
        description: "Understand tenths and hundredths.",
        goal_text: "I want to understand decimal place value.",
        difficulty: "medium",
      },
      {
        id: "comparing-decimals",
        title: "Comparing decimals",
        description: "Order and compare decimal numbers.",
        goal_text: "I want to compare and order decimal numbers.",
        difficulty: "medium",
      },
      {
        id: "converting-fractions-decimals",
        title: "Converting fractions and decimals",
        description: "Turn fractions into decimals and back.",
        goal_text: "I want to convert between fractions and decimals.",
        difficulty: "hard",
      },
      {
        id: "understanding-percentages",
        title: "Understanding percentages",
        description: "See percentages as parts out of 100.",
        goal_text: "I want to understand what percentages mean.",
        difficulty: "hard",
      },
    ],
  },
  {
    id: "geometry",
    title: "Geometry",
    description: "Explore shapes, angles, and space.",
    icon: "category",
    subtopics: [
      {
        id: "2d-shapes",
        title: "2D shapes",
        description: "Name and describe flat shapes.",
        goal_text: "I want to recognize and describe 2D shapes.",
        difficulty: "easy",
      },
      {
        id: "angles",
        title: "Angles",
        description: "Learn about right, acute, and obtuse angles.",
        goal_text: "I want to understand and identify different angles.",
        difficulty: "medium",
      },
      {
        id: "perimeter",
        title: "Perimeter",
        description: "Measure the distance around a shape.",
        goal_text: "I want to find the perimeter of shapes.",
        difficulty: "medium",
      },
      {
        id: "area",
        title: "Area",
        description: "Measure the space inside a shape.",
        goal_text: "I want to find the area of shapes.",
        difficulty: "hard",
      },
    ],
  },
  {
    id: "measurement",
    title: "Measurement",
    description: "Measure length, weight, time, and more.",
    icon: "straighten",
    subtopics: [
      {
        id: "length-distance",
        title: "Length and distance",
        description: "Measure how long or far something is.",
        goal_text: "I want to measure length and distance.",
        difficulty: "easy",
      },
      {
        id: "weight-mass",
        title: "Weight and mass",
        description: "Measure how heavy something is.",
        goal_text: "I want to measure weight and mass.",
        difficulty: "medium",
      },
      {
        id: "time",
        title: "Time",
        description: "Tell the time and work with durations.",
        goal_text: "I want to read time and work out durations.",
        difficulty: "medium",
      },
      {
        id: "units-conversions",
        title: "Units and conversions",
        description: "Change between units like cm and m.",
        goal_text: "I want to convert between different units of measurement.",
        difficulty: "hard",
      },
    ],
  },
  {
    id: "word-problems",
    title: "Word Problems",
    description: "Turn real-life stories into math.",
    icon: "quiz",
    subtopics: [
      {
        id: "understanding-the-question",
        title: "Understanding the question",
        description: "Find what a word problem is really asking.",
        goal_text: "I want to understand what a word problem is asking.",
        difficulty: "easy",
      },
      {
        id: "choosing-the-operation",
        title: "Choosing the right operation",
        description: "Decide whether to add, subtract, multiply, or divide.",
        goal_text: "I want to choose the right operation for a word problem.",
        difficulty: "medium",
      },
      {
        id: "multi-step-problems",
        title: "Multi-step problems",
        description: "Solve problems that need more than one step.",
        goal_text: "I want to solve multi-step word problems.",
        difficulty: "hard",
      },
      {
        id: "checking-your-answer",
        title: "Checking your answer",
        description: "Make sure your answer makes sense.",
        goal_text: "I want to check that my answers are reasonable and correct.",
        difficulty: "medium",
      },
    ],
  },
];

export function getTopicById(id: string | undefined): MathTopic | undefined {
  if (!id) return undefined;
  return MATH_CURRICULUM.find((t) => t.id === id);
}
