import pygame
import sys
import math
import os
from pymongo import MongoClient

pygame.init()

# ================================================================
# CONFIG — Tous les parametres modifiables ici
# ================================================================
CONFIG = {
    # Grille
    'grid_size_default' : 12,
    'grid_size_min'     : 5,
    'grid_size_max'     : 30,

    # Regle de victoire
    'align_length'      : 5,    # points consecutifs pour un alignement

    # Canon
    'power_min'         : 1,    # puissance minimale  (Ctrl + power_min)
    'power_max'         : 9,    # puissance maximale  (Ctrl + power_max)

    # Rendu
    'cell'              : 44,   # taille d'une case en pixels
    'pad'               : 65,   # marge autour de la grille
    'hud_h'             : 80,   # hauteur du bandeau HUD en haut
    'fps'               : 60,

    # Couleurs (R, G, B)
    'BG'    : (13,  17,  23),
    'GRID'  : (33,  38,  45),
    'BLUE'  : (88,  166, 255),
    'RED'   : (255, 80,  80),
    'GOLD'  : (240, 192, 0),
    'BALL'  : (255, 215, 0),
    'TEXT'  : (230, 237, 243),
    'GRAY'  : (139, 148, 158),
    'GREEN' : (35,  134, 54),
    'AMBER' : (158, 106, 3),
    'DRED'  : (218, 54,  51),

    # Animation balle
    'ball_frames'    : 45,    # duree en frames (plus = plus lent)
    'ball_radius'    : 8,
    'ball_amplitude' : 0.25,  # amplitude de la sinusoide
    'ball_frequency' : 4,     # nombre de lobes

    # MongoDB
    'mongo_uri'  : os.getenv('MONGO_URI', 'mongodb://localhost:27017'),
    'db_name'    : 'gamepoint',
    'collection' : 'saves',
    'save_slot'  : 'default',
}

# ================================================================
# BASE DE DONNEES — MongoDB
# ================================================================
def get_col():
    client = MongoClient(CONFIG['mongo_uri'], serverSelectionTimeoutMS=3000)
    return client[CONFIG['db_name']][CONFIG['collection']]

def db_save(state):
    data = {
        'slot'      : CONFIG['save_slot'],
        'N'         : state['N'],
        'grid'      : state['grid'],
        'can_row'   : state['can_row'],
        'scores'    : state['scores'],
        'align_set' : list(state['align_set']),
        'turn'      : state['turn'],
    }
    get_col().replace_one({'slot': CONFIG['save_slot']}, data, upsert=True)

def db_load():
    doc = get_col().find_one({'slot': CONFIG['save_slot']}, {'_id': 0, 'slot': 0})
    return doc

# ================================================================
# LOGIQUE — Alignements et score
# ================================================================
DIRS = [(0, 1), (1, 0), (1, 1), (1, -1)]

def recompute(state):
    N    = state['N']
    grid = state['grid']
    L    = CONFIG['align_length']
    aset = set()

    for r in range(N):
        for c in range(N):
            v = grid[r][c]
            if not v:
                continue
            for dr, dc in DIRS:
                cells, ok = [], True
                for k in range(L):
                    nr, nc = r + dr * k, c + dc * k
                    if not (0 <= nr < N and 0 <= nc < N) or grid[nr][nc] != v:
                        ok = False
                        break
                    cells.append(f'{nr},{nc}')
                if ok:
                    aset.update(cells)

    scores = [0, 0]
    for pl in range(1, 3):
        for dr, dc in DIRS:
            for r in range(N):
                for c in range(N):
                    if grid[r][c] != pl:
                        continue
                    pr, pc = r - dr, c - dc
                    if 0 <= pr < N and 0 <= pc < N and grid[pr][pc] == pl:
                        continue
                    length, nr, nc = 0, r, c
                    while 0 <= nr < N and 0 <= nc < N and grid[nr][nc] == pl:
                        length += 1
                        nr += dr
                        nc += dc
                    if length >= L:
                        scores[pl - 1] += 1

    state['align_set'] = aset
    state['scores']    = scores

def power_to_col(p, N):
    lo, hi = CONFIG['power_min'], CONFIG['power_max']
    return round((p - lo) / (hi - lo) * (N - 1))

# ================================================================
# HELPERS GEOMETRIE
# ================================================================
def col_x(c): return CONFIG['pad'] + c * CONFIG['cell'] + CONFIG['cell'] // 2
def row_y(r): return CONFIG['pad'] + r * CONFIG['cell'] + CONFIG['cell'] // 2 + CONFIG['hud_h']

# ================================================================
# RENDU
# ================================================================
def draw_game(screen, state, fonts, toast, ball_anim):
    N  = state['N']
    C  = CONFIG['cell']
    P  = CONFIG['pad']
    H  = CONFIG['hud_h']
    W  = N * C + P * 2
    TH = H + N * C + P * 2

    screen.fill(CONFIG['BG'])

    # --- HUD bandeau ---
    pygame.draw.rect(screen, (22, 27, 34), (0, 0, W, H - 4))
    s0 = fonts['hud'].render(f"Bleu : {state['scores'][0]}", True, CONFIG['BLUE'])
    s1 = fonts['hud'].render(f"Rouge : {state['scores'][1]}", True, CONFIG['RED'])
    tc = CONFIG['BLUE'] if state['turn'] == 0 else CONFIG['RED']
    tl = fonts['hud'].render('Tour : BLEU' if state['turn'] == 0 else 'Tour : ROUGE', True, tc)
    screen.blit(s0, (16, 12))
    screen.blit(tl, (W // 2 - tl.get_width() // 2, 12))
    screen.blit(s1, (W - 16 - s1.get_width(), 12))

    buttons = _draw_buttons(screen, fonts, W, 40)

    # --- Barre info ---
    cols = sorted({power_to_col(p, N) + 1 for p in range(CONFIG['power_min'], CONFIG['power_max'] + 1)})
    msg  = toast if toast else (
        f"Clic: placer  |  Fleches: viser (rangee {state['can_row'][state['turn']] + 1})"
        f"  |  Ctrl+{CONFIG['power_min']}-{CONFIG['power_max']}: tirer"
        f"  |  Colonnes: {', '.join(map(str, cols))}"
    )
    info = fonts['small'].render(msg, True, CONFIG['GRAY'])
    screen.blit(info, (W // 2 - info.get_width() // 2, H + P - 20))

    # --- Lignes de grille ---
    for i in range(N + 1):
        pygame.draw.line(screen, CONFIG['GRID'], (P, H + P + i * C), (P + N * C, H + P + i * C))
        pygame.draw.line(screen, CONFIG['GRID'], (P + i * C, H + P), (P + i * C, H + P + N * C))

    # --- Numeros de colonnes ---
    for c in range(N):
        num = fonts['tiny'].render(str(c + 1), True, (72, 79, 88))
        screen.blit(num, (col_x(c) - num.get_width() // 2, H + P - 16))

    # --- Surlignage cellules en alignement ---
    for k in state['align_set']:
        r, c  = map(int, k.split(','))
        base  = CONFIG['BLUE'] if state['grid'][r][c] == 1 else CONFIG['RED']
        surf  = pygame.Surface((C - 2, C - 2), pygame.SRCALPHA)
        surf.fill((*base, 46))
        screen.blit(surf, (P + c * C + 1, H + P + r * C + 1))

    # --- Points ---
    for r in range(N):
        for c in range(N):
            v = state['grid'][r][c]
            if not v:
                continue
            color = CONFIG['BLUE'] if v == 1 else CONFIG['RED']
            pygame.draw.circle(screen, color, (col_x(c), row_y(r)), int(C * 0.32))
            if f'{r},{c}' in state['align_set']:
                pygame.draw.circle(screen, CONFIG['GOLD'], (col_x(c), row_y(r)), int(C * 0.32), 2)

    # --- Canons ---
    _draw_cannon(screen, state, 0)
    _draw_cannon(screen, state, 1)

    # --- Balle en vol ---
    if ball_anim and ball_anim['active']:
        t   = ball_anim['frame'] / ball_anim['total']
        dx  = ball_anim['ex'] - ball_anim['sx']
        dy  = ball_anim['ey'] - ball_anim['sy']
        lng = math.sqrt(dx * dx + dy * dy) or 1
        amp = min(lng * CONFIG['ball_amplitude'], C * 2.5)
        lx  = ball_anim['sx'] + dx * t
        ly  = ball_anim['sy'] + dy * t
        perp = math.sin(t * math.pi * CONFIG['ball_frequency']) * amp * (1 - t)
        px  = -dy / lng * perp
        py  =  dx / lng * perp
        pygame.draw.circle(screen, CONFIG['BALL'], (int(lx + px), int(ly + py)), CONFIG['ball_radius'])

    return buttons

def _draw_cannon(screen, state, p):
    N  = state['N']
    C  = CONFIG['cell']
    P  = CONFIG['pad']
    cy = row_y(state['can_row'][p])
    color  = CONFIG['BLUE'] if p == 0 else CONFIG['RED']
    border = CONFIG['GOLD'] if state['turn'] == p else CONFIG['GRID']

    if p == 0:
        cx = P - 30
        pygame.draw.rect(screen, color,  (cx - 14, cy - 9, 28, 18), border_radius=4)
        pygame.draw.rect(screen, border, (cx - 14, cy - 9, 28, 18), 2, border_radius=4)
        pygame.draw.rect(screen, color,  (cx + 10, cy - 4, 16, 8))
    else:
        cx = P + N * C + 30
        pygame.draw.rect(screen, color,  (cx - 14, cy - 9, 28, 18), border_radius=4)
        pygame.draw.rect(screen, border, (cx - 14, cy - 9, 28, 18), 2, border_radius=4)
        pygame.draw.rect(screen, color,  (cx - 26, cy - 4, 16, 8))

def _draw_buttons(screen, fonts, W, y):
    btns = {}
    specs = [
        ('save', 'Sauvegarder', CONFIG['GREEN'], W // 2 - 200),
        ('load', 'Charger',     CONFIG['AMBER'], W // 2 - 60),
        ('end',  'Terminer',    CONFIG['DRED'],  W // 2 + 60),
    ]
    for key, label, color, x in specs:
        rect = pygame.Rect(x, y, 120, 28)
        pygame.draw.rect(screen, color, rect, border_radius=5)
        txt = fonts['small'].render(label, True, CONFIG['TEXT'])
        screen.blit(txt, (rect.centerx - txt.get_width() // 2, rect.centery - txt.get_height() // 2))
        btns[key] = rect
    return btns

def draw_end_modal(screen, state, fonts, W, TH):
    overlay = pygame.Surface((W, TH), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))

    mw, mh = 360, 175
    mx, my = W // 2 - mw // 2, TH // 2 - mh // 2
    pygame.draw.rect(screen, (22, 27, 34), (mx, my, mw, mh), border_radius=12)
    pygame.draw.rect(screen, (48, 54, 61), (mx, my, mw, mh), 1, border_radius=12)

    s0, s1 = state['scores']
    if   s0 > s1: winner = 'Bleu gagne !'
    elif s1 > s0: winner = 'Rouge gagne !'
    else:          winner = 'Egalite !'

    title = fonts['hud'].render(winner, True, CONFIG['TEXT'])
    body  = fonts['small'].render(f"Bleu : {s0} alignement(s)   Rouge : {s1} alignement(s)", True, CONFIG['GRAY'])
    screen.blit(title, (W // 2 - title.get_width() // 2, my + 28))
    screen.blit(body,  (W // 2 - body.get_width()  // 2, my + 72))

    ok = pygame.Rect(W // 2 - 50, my + 118, 100, 34)
    pygame.draw.rect(screen, CONFIG['GREEN'], ok, border_radius=6)
    ok_txt = fonts['small'].render('OK', True, CONFIG['TEXT'])
    screen.blit(ok_txt, (ok.centerx - ok_txt.get_width() // 2, ok.centery - ok_txt.get_height() // 2))
    return ok

# ================================================================
# ECRAN DE CONFIGURATION
# ================================================================
def setup_screen():
    screen = pygame.display.set_mode((420, 290))
    pygame.display.set_caption('Game Point')
    f_big = pygame.font.SysFont('Arial', 26, bold=True)
    f_med = pygame.font.SysFont('Arial', 18)
    f_sml = pygame.font.SysFont('Arial', 13)
    val   = str(CONFIG['grid_size_default'])

    while True:
        screen.fill(CONFIG['BG'])
        t = f_big.render('Game Point', True, CONFIG['BLUE'])
        screen.blit(t, (210 - t.get_width() // 2, 40))
        lbl = f_med.render('Taille de la grille :', True, CONFIG['TEXT'])
        screen.blit(lbl, (210 - lbl.get_width() // 2, 105))

        inp = pygame.Rect(155, 135, 110, 36)
        pygame.draw.rect(screen, (22, 27, 34), inp, border_radius=6)
        pygame.draw.rect(screen, CONFIG['BLUE'], inp, 2, border_radius=6)
        iv = f_med.render(val, True, CONFIG['TEXT'])
        screen.blit(iv, (inp.centerx - iv.get_width() // 2, inp.centery - iv.get_height() // 2))

        hint = f_sml.render(f"Recommande : {CONFIG['grid_size_min']} a {CONFIG['grid_size_max']}", True, CONFIG['GRAY'])
        screen.blit(hint, (210 - hint.get_width() // 2, 182))

        btn = pygame.Rect(130, 215, 160, 44)
        pygame.draw.rect(screen, CONFIG['GREEN'], btn, border_radius=8)
        bt = f_med.render('Demarrer', True, CONFIG['TEXT'])
        screen.blit(bt, (btn.centerx - bt.get_width() // 2, btn.centery - bt.get_height() // 2))

        pygame.display.flip()

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_RETURN:
                    return _parse_n(val)
                elif e.key == pygame.K_BACKSPACE:
                    val = val[:-1]
                elif e.unicode.isdigit() and len(val) < 3:
                    val += e.unicode
            if e.type == pygame.MOUSEBUTTONDOWN and btn.collidepoint(e.pos):
                return _parse_n(val)

def _parse_n(s):
    try:
        n = int(s)
    except ValueError:
        n = CONFIG['grid_size_default']
    return max(CONFIG['grid_size_min'], min(CONFIG['grid_size_max'], n))

# ================================================================
# BOUCLE PRINCIPALE
# ================================================================
def main():
    N = setup_screen()
    C = CONFIG['cell']
    P = CONFIG['pad']
    H = CONFIG['hud_h']
    W  = N * C + P * 2
    TH = H + N * C + P * 2

    screen = pygame.display.set_mode((W, TH))
    pygame.display.set_caption('Game Point')
    clock  = pygame.time.Clock()

    fonts = {
        'hud'  : pygame.font.SysFont('Arial', 15, bold=True),
        'small': pygame.font.SysFont('Arial', 13),
        'tiny' : pygame.font.SysFont('Arial', 10),
    }

    state = {
        'N'        : N,
        'grid'     : [[0] * N for _ in range(N)],
        'can_row'  : [N // 2, N // 2],
        'scores'   : [0, 0],
        'align_set': set(),
        'turn'     : 0,
    }
    recompute(state)

    ball_anim   = None
    toast       = ''
    toast_timer = 0
    show_end    = False
    ok_rect     = None
    buttons     = {}

    # --- Helpers locaux ---
    def set_toast(msg):
        nonlocal toast, toast_timer
        toast = msg
        toast_timer = CONFIG['fps'] * 2  # 2 secondes

    def start_fire(target_col):
        nonlocal ball_anim
        tr = state['can_row'][state['turn']]
        p  = state['turn']
        sx = P - 20 if p == 0 else P + N * C + 20
        sy = row_y(state['can_row'][p])

        def on_done():
            opp = 2 if state['turn'] == 0 else 1
            if state['grid'][tr][target_col] == opp:
                if f'{tr},{target_col}' in state['align_set']:
                    set_toast('Point protege - alignement en cours')
                else:
                    state['grid'][tr][target_col] = 0
                    recompute(state)
            state['turn'] = 1 - state['turn']

        ball_anim = {
            'active': True,
            'frame' : 0,
            'total' : CONFIG['ball_frames'],
            'sx': sx, 'sy': sy,
            'ex': col_x(target_col),
            'ey': row_y(tr),
            'on_done': on_done,
        }

    def apply_load(doc):
        nonlocal N, W, TH, screen
        state['N']         = doc['N']
        state['grid']      = doc['grid']
        state['can_row']   = doc['can_row']
        state['scores']    = doc['scores']
        state['align_set'] = set(doc['align_set'])
        state['turn']      = doc['turn']
        N  = state['N']
        W  = N * C + P * 2
        TH = H + N * C + P * 2
        screen = pygame.display.set_mode((W, TH))

    # --- Boucle ---
    while True:
        clock.tick(CONFIG['fps'])

        # Timer toast
        if toast_timer > 0:
            toast_timer -= 1
            if toast_timer == 0:
                toast = ''

        # Avancer l'animation
        if ball_anim and ball_anim['active']:
            ball_anim['frame'] += 1
            if ball_anim['frame'] >= ball_anim['total']:
                ball_anim['active'] = False
                ball_anim['on_done']()
                ball_anim = None

        busy = ball_anim is not None

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            # Modal fin de partie
            if show_end:
                if e.type == pygame.MOUSEBUTTONDOWN and ok_rect and ok_rect.collidepoint(e.pos):
                    show_end = False
                continue

            if busy:
                continue

            # Clavier
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_UP:
                    state['can_row'][state['turn']] = max(0, state['can_row'][state['turn']] - 1)
                elif e.key == pygame.K_DOWN:
                    state['can_row'][state['turn']] = min(N - 1, state['can_row'][state['turn']] + 1)
                elif e.mod & pygame.KMOD_CTRL and pygame.K_1 <= e.key <= pygame.K_9:
                    p = e.key - pygame.K_0
                    if CONFIG['power_min'] <= p <= CONFIG['power_max']:
                        start_fire(power_to_col(p, N))

            # Souris
            if e.type == pygame.MOUSEBUTTONDOWN:
                mx, my = e.pos

                if 'save' in buttons and buttons['save'].collidepoint(mx, my):
                    try:
                        db_save(state)
                        set_toast('Partie sauvegardee')
                    except Exception as ex:
                        set_toast(f'Erreur MongoDB : {ex}')

                elif 'load' in buttons and buttons['load'].collidepoint(mx, my):
                    try:
                        doc = db_load()
                        if doc:
                            apply_load(doc)
                            set_toast('Partie chargee')
                        else:
                            set_toast('Aucune sauvegarde trouvee')
                    except Exception as ex:
                        set_toast(f'Erreur MongoDB : {ex}')

                elif 'end' in buttons and buttons['end'].collidepoint(mx, my):
                    show_end = True

                else:
                    # Clic sur la grille → placer un point
                    gx = mx - P
                    gy = my - P - H
                    c_ = gx // C
                    r_ = gy // C
                    if 0 <= c_ < N and 0 <= r_ < N and state['grid'][r_][c_] == 0:
                        state['grid'][r_][c_] = state['turn'] + 1
                        recompute(state)
                        state['turn'] = 1 - state['turn']

        # Rendu
        buttons = draw_game(screen, state, fonts, toast, ball_anim)
        if show_end:
            ok_rect = draw_end_modal(screen, state, fonts, W, TH)
        pygame.display.flip()

if __name__ == '__main__':
    main()
