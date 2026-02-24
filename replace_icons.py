import os
import re

icon_map = {
    'fa-chevron-left': 'ph-bold ph-caret-left',
    'fa-gem': 'ph-fill ph-diamond',
    'fa-star': 'ph-fill ph-star',
    'fa-user-friends': 'ph-bold ph-users',
    'fa-clock': 'ph-bold ph-clock',
    'fa-chart-line': 'ph-bold ph-trend-up',
    'fa-shield-alt': 'ph-fill ph-shield-check',
    'fa-dice': 'ph-fill ph-dice-five',
    'fa-heart': 'ph-fill ph-heart',
    'fa-cat': 'ph-fill ph-cat',
    'fa-hat-wizard': 'ph-fill ph-magic-wand',
    'fa-layer-group': 'ph-fill ph-cards',
    'fa-palette': 'ph-fill ph-palette',
    'fa-times': 'ph-bold ph-x',
    'fa-arrow-left': 'ph-bold ph-arrow-left',
    'fa-users': 'ph-bold ph-users',
    'fa-door-open': 'ph-bold ph-door-open',
    'fa-play': 'ph-fill ph-play',
    'fa-trash-alt': 'ph-bold ph-trash',
    'fa-store': 'ph-bold ph-storefront',
    'fa-gavel': 'ph-bold ph-scales',
    'fa-check': 'ph-bold ph-check',
    'fa-handshake': 'ph-bold ph-handshake',
    'fa-history': 'ph-bold ph-clock-counter-clockwise',
    'fa-redo': 'ph-bold ph-arrow-clockwise',
    'fa-user': 'ph-fill ph-user',
    'fa-user-circle': 'ph-fill ph-user-circle',
    'fa-sign-in-alt': 'ph-bold ph-sign-in',
    'fa-check-circle': 'ph-fill ph-check-circle',
    'fa-skull-crossbones': 'ph-fill ph-skull',
    'fa-plus': 'ph-bold ph-plus',
    'fa-flag-checkered': 'ph-fill ph-flag-checkered',
    'fa-book-open': 'ph-bold ph-book-open',
    'fa-chevron-right': 'ph-bold ph-caret-right',
    'fa-pen': 'ph-bold ph-pencil-simple',
    'fa-minus': 'ph-bold ph-minus'
}

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    for fa, ph in icon_map.items():
        content = re.sub(r'fas\s+' + fa, ph, content)
        content = re.sub(r'far\s+' + fa, ph, content)
        content = re.sub(r'fa\s+' + fa, ph, content)
        content = re.sub(r'fa-solid\s+' + fa, ph, content)

    # Handle JS concatenation in ModernArt: '<i class="fas ' + (condition ? 'fa-user' : 'fa-user-circle') + '"' => '<i class="' + (condition ? 'ph-fill ph-user' : 'ph-fill ph-user-circle') + '"'
    content = content.replace('class="fas \'', 'class="\'')
    content = content.replace("'fa-user'", "'ph-fill ph-user'")
    content = content.replace("'fa-user-circle'", "'ph-fill ph-user-circle'")

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")

if __name__ == '__main__':
    base_dir = r"c:\Program Files\code\bgp"
    for root, dirs, files in os.walk(base_dir):
        if 'node_modules' in root or '.git' in root or '.venv' in root:
            continue
        for file in files:
            if file.endswith('.html'):
                process_file(os.path.join(root, file))
