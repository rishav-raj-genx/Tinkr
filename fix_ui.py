import re

with open('index.html', 'r') as f:
    html = f.read()

# Replace emojis with Material Icons HTML
replacements = {
    '✨': '<span class="material-icons setup-logo-icon">graphic_eq</span>',
    '🧠': '<span class="material-icons">psychology</span>',
    '📈': '<span class="material-icons">insights</span>',
    '📊': '<span class="material-icons">bar_chart</span>',
    '⚠️': '<span class="material-icons">warning</span>',
    '✅': '<span class="material-icons">check_circle</span>',
    '👍': '<span class="material-icons">thumb_up</span>',
    '❌': '<span class="material-icons">cancel</span>',
    '💡': '<span class="material-icons">lightbulb</span>',
    '😰': '<span class="material-icons">sentiment_very_dissatisfied</span>',
    '😟': '<span class="material-icons">sentiment_dissatisfied</span>',
    '😴': '<span class="material-icons">bedtime</span>',
    '😌': '<span class="material-icons">sentiment_satisfied_alt</span>',
    '❓': '<span class="material-icons">help_outline</span>',
    '✦': '<span class="material-icons" style="font-size:12px;">arrow_right</span>'
}

for emoji, replacement in replacements.items():
    html = html.replace(emoji, replacement)

# Update CSS for a more polished look
# We will replace the root variables and some classes to make it look like a premium app.
css_updates = {
    '--bg-color: #0a0e1a;': '--bg-color: #121212;',
    '--bg-secondary: #0f172a;': '--bg-secondary: #1e1e1e;',
    '--surface: #1e293b;': '--surface: #2c2c2c;',
    '--surface-elevated: #253349;': '--surface-elevated: #383838;',
    '--text-main: #f8fafc;': '--text-main: #e0e0e0;',
    '--accent: #3b82f6;': '--accent: #bb86fc;',
    '--accent-glow: rgba(59, 130, 246, 0.3);': '--accent-glow: rgba(187, 134, 252, 0.3);',
    'background: linear-gradient(135deg, var(--accent), #2563eb);': 'background: var(--accent); color: #000;',
    'background: linear-gradient(135deg, #334155, #3b4a63);': 'background: #333333; color: #e0e0e0;',
    'background: rgba(59, 130, 246, 0.08);': 'background: rgba(187, 134, 252, 0.08);',
    'border: 1px solid rgba(59, 130, 246, 0.15);': 'border: 1px solid rgba(187, 134, 252, 0.15);',
    'color: #93bbfc;': 'color: #bb86fc;'
}

for old, new in css_updates.items():
    html = html.replace(old, new)

# Let's fix the setup logo class since we injected a material icon
html = html.replace('<div class="setup-logo"><span class="material-icons setup-logo-icon">graphic_eq</span></div>', 
                    '<div class="setup-logo"><span class="material-icons" style="font-size: 3rem; color: var(--accent);">graphic_eq</span></div>')

with open('index.html', 'w') as f:
    f.write(html)
