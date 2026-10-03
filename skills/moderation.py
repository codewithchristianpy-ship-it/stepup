"""
Skill-aware content moderation for community lessons.

Three verdicts:
  pass    → publish immediately (if user is trusted) or queue for review
  review  → save as pending; admin or auto-approval decides later
  reject  → don't save; show user what went wrong

Rules are category-specific: a Python lesson must look like code,
a Cooking lesson must look like a recipe, etc.
"""
import re
from collections import Counter


# ============================================================
# GENERIC RULES (apply to ALL lessons)
# ============================================================

BANNED_WORDS = {
    # Profanity
    'fuck', 'shit', 'bitch', 'asshole', 'bastard',
    # Abuse
    'idiot', 'stupid', 'dumb', 'moron', 'retard',
    # Scam markers
    'click here to win', 'send money', 'western union',
    'bitcoin giveaway', 'free money',
    # Sexual content
    'nude', 'porn', 'xxx', 'sex video',
    # URL shorteners commonly used for spam
    'bit.ly/', 'tinyurl.com/',
}

SUSPICIOUS_PATTERNS = [
    (r'\b(buy now|order now|limited offer)\b', 'Promotional language detected.'),
    (r'\b(whatsapp me|dm me|call me for)\b', 'Contact solicitation detected.'),
    (r'\b(click\s+the\s+link|visit\s+my\s+site)\b', 'Spam link pattern detected.'),
    (r'\b(earn \$?\d+ (per|a) (day|hour|week))\b', 'Money-making spam detected.'),
]


# ============================================================
# CATEGORY-SPECIFIC RULES
# ============================================================

CATEGORY_RULES = {
    'technology': {
        'required_any': [
            'code', 'program', 'function', 'variable', 'loop', 'python',
            'javascript', 'html', 'css', 'data', 'app', 'software',
            'screen', 'button', 'click', 'file', 'folder', 'error',
            'formula', 'excel', 'cell', 'spreadsheet', 'ai', 'prompt',
            'phone', 'android', 'iphone', 'wifi', 'settings',
            'user', 'system', 'input', 'output', 'print', 'return',
            'install', 'download', 'browser', 'internet', 'network',
        ],
        'forbidden_patterns': [
            (r'\b(will you marry|i love you baby)\b',
             'Romantic content is not appropriate for a technology lesson.'),
        ],
        'min_word_count': 50,
    },
    'language': {
        'required_any': [
            'hello', 'bonjour', 'hola', 'greeting', 'word', 'sentence',
            'pronounce', 'grammar', 'phrase', 'say', 'speak', 'listen',
            'write', 'read', 'translate', 'conversation', 'vocabulary',
            'verb', 'noun', 'goodbye', 'thank', 'please', 'language',
            'english', 'french', 'spanish', 'meaning',
        ],
        'forbidden_patterns': [
            (r'def\s+\w+\s*\(', 'Code syntax detected — this looks misplaced in a language lesson.'),
            (r'<\w+>.*</\w+>', 'HTML detected — this looks misplaced in a language lesson.'),
        ],
        'min_word_count': 50,
    },
    'math': {
        'required_any': [
            'number', 'add', 'subtract', 'multiply', 'divide', 'equals',
            'fraction', 'decimal', 'equation', 'solve', 'answer', 'value',
            'sum', 'difference', 'product', 'quotient', 'variable',
            'zero', 'one', 'two', 'hundred', 'thousand',
            'percent', 'calculate', 'math',
        ],
        'forbidden_patterns': [],
        'min_word_count': 40,
        'require_numbers': True,
    },
    'career': {
        'required_any': [
            'job', 'work', 'career', 'interview', 'cv', 'resume', 'salary',
            'employer', 'employee', 'company', 'skill', 'profession',
            'apply', 'application', 'offer', 'hire', 'manager', 'team',
            'money', 'budget', 'save', 'invest', 'savings', 'debt',
            'goal', 'plan', 'success', 'business', 'customer',
        ],
        'forbidden_patterns': [],
        'min_word_count': 60,
    },
    'practical': {
        'required_any': [
            'step', 'mix', 'cook', 'prepare', 'add', 'boil', 'fry',
            'wash', 'clean', 'repair', 'fix', 'turn', 'press', 'hold',
            'first aid', 'emergency', 'safety', 'careful',
            'ingredient', 'heat', 'water', 'oil', 'salt', 'pan', 'pot',
            'hands', 'help', 'tools', 'kitchen', 'recipe',
        ],
        'forbidden_patterns': [
            (r'def\s+\w+\s*\(', 'Code syntax detected — this looks misplaced in a practical lesson.'),
        ],
        'min_word_count': 50,
    },
    'creative': {
        'required_any': [
            'draw', 'color', 'paint', 'design', 'create', 'art', 'shape',
            'line', 'shade', 'sketch', 'edit', 'video', 'clip', 'music',
            'film', 'record', 'photo', 'canvas', 'brush', 'visual',
            'caption', 'transition', 'effect', 'style', 'look',
            'camera', 'light', 'shadow', 'angle', 'film',
        ],
        'forbidden_patterns': [],
        'min_word_count': 50,
    },
    'health': {
        'required_any': [
            'body', 'health', 'stress', 'sleep', 'exercise', 'muscle',
            'breath', 'calm', 'mind', 'feeling', 'rest', 'walk',
            'pain', 'relax', 'energy', 'mood', 'anxiety', 'stretch',
            'water', 'food', 'heart', 'brain', 'wellness', 'mental',
            'doctor', 'medicine', 'healthy', 'daily',
        ],
        'forbidden_patterns': [
            (r'\b(prescribe|dosage|mg of|prescription)\b',
             'Medical prescriptions are not allowed here. Share general wellness tips only.'),
            (r'\b(cure cancer|treat disease|diagnose)\b',
             'Medical claims are not allowed. Share general wellness tips only.'),
        ],
        'min_word_count': 50,
    },
    'civic': {
        'required_any': [
            'community', 'people', 'neighbor', 'group', 'meeting',
            'organize', 'volunteer', 'issue', 'change', 'power',
            'leader', 'action', 'petition', 'vote', 'public', 'together',
            'plan', 'goal', 'team', 'movement', 'local', 'government',
            'campaign', 'support', 'help', 'solve', 'problem',
            'community', 'change', 'voice',
        ],
        'forbidden_patterns': [],
        'min_word_count': 60,
    },
}


# ============================================================
# MAIN FUNCTION
# ============================================================

def check_lesson(title, content, skill):
    """
    Skill-aware moderation.

    Returns:
      ('pass', None)         → publish if user trusted, else queue for review
      ('review', reason)     → queue for review
      ('reject', reason)     → reject with reason shown to user
    """
    title = (title or '').strip()
    content = (content or '').strip()
    combined = f"{title} {content}".lower()
    category = getattr(skill, 'category', 'technology')
    skill_name = getattr(skill, 'name', 'this skill')

    # ============ LAYER 1: HARD REJECTS ============

    if not title or not content:
        return ('reject', "Title and content cannot be empty.")

    if len(title) < 5:
        return ('reject', "Title is too short — make it descriptive.")

    if len(content) < 100:
        return ('reject', "Lesson is too short. Aim for 200+ words so learners get real value.")

    if len(content) > 10000:
        return ('reject', "Lesson is too long. Keep it under 10,000 characters.")

    # Gibberish check: too few unique characters
    if len(set(content.replace(" ", ""))) < 10:
        return ('reject', "Content looks like gibberish. Please write a real lesson.")

    # Gibberish check: no vowels in long text
    letters = re.findall(r'[a-zA-Z]', content)
    if len(letters) > 50:
        vowels = sum(1 for c in letters if c.lower() in 'aeiou')
        if vowels / len(letters) < 0.15:
            return ('reject', "Content doesn't look like readable text.")

    # ALL CAPS shouting
    if len(content) > 50:
        uppercase_ratio = sum(1 for c in content if c.isupper()) / len(content)
        if uppercase_ratio > 0.6:
            return ('reject', "Please don't write in ALL CAPS. It looks like shouting.")

    # ============ LAYER 2: BANNED WORDS ============

    for word in BANNED_WORDS:
        if word in combined:
            return ('reject', "Your lesson contains language that isn't allowed. Please rewrite.")

    # ============ LAYER 3: SUSPICIOUS PATTERNS ============

    for pattern, reason in SUSPICIOUS_PATTERNS:
        if re.search(pattern, combined):
            return ('review', reason + " A moderator will review before publishing.")

    # Too many URLs
    url_count = len(re.findall(r'https?://', content))
    if url_count > 2:
        return ('review', "Too many external links. A moderator will review before publishing.")

    # ============ LAYER 4: CATEGORY CHECKS ============

    rules = CATEGORY_RULES.get(category, {})

    # 4a. Minimum word count for this category
    word_count = len(content.split())
    min_words = rules.get('min_word_count', 40)
    if word_count < min_words:
        return ('review',
            f"Lesson is a bit short for {skill_name}. A moderator will review it.")

    # 4b. Forbidden patterns for this category
    for pattern, reason in rules.get('forbidden_patterns', []):
        if re.search(pattern, content, re.IGNORECASE):
            return ('reject', reason)

    # 4c. Required keywords — does content match this skill?
    required_any = rules.get('required_any', [])
    if required_any:
        found = any(word in combined for word in required_any)
        if not found:
            return ('review',
                f"This lesson doesn't seem related to {skill_name}. "
                f"A moderator will review it before publishing.")

    # 4d. Math must have numbers
    if rules.get('require_numbers'):
        if not re.search(r'\d', content):
            return ('review',
                "Math lessons should contain numbers or formulas. "
                "A moderator will review it before publishing.")

    # ============ LAYER 5: REPEAT-WORD SPAM ============

    words = re.findall(r'\b\w{4,}\b', content.lower())
    if words:
        most_common_word, count = Counter(words).most_common(1)[0]
        if count > 20 and count / len(words) > 0.15:
            return ('review',
                "Content repeats the same words a lot. A moderator will review it.")

    # ============ PASS ============
    return ('pass', None)


# ============================================================
# QUALITY SCORE (0-100)
# ============================================================

def quality_score(title, content, skill=None):
    """Returns a score 0-100 based on quality signals. Used for admin sorting."""
    score = 50

    word_count = len(content.split())
    if word_count >= 100:
        score += 10
    if word_count >= 200:
        score += 10
    if word_count >= 400:
        score += 10

    if '\n' in content:
        score += 5

    if re.search(r'\n\s{2,}', content):
        score += 5

    if 20 <= len(title) <= 100:
        score += 5

    if content.isupper():
        score -= 30

    # Category-specific bonus
    if skill:
        rules = CATEGORY_RULES.get(skill.category, {})
        required = rules.get('required_any', [])
        if required:
            matches = sum(1 for word in required if word in content.lower())
            score += min(matches * 2, 15)

    return max(0, min(100, score))