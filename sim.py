import pygame
import random
import math as meth
import numpy as np
import sys
from pygame.locals import *
import time

# Константы
MAX_DIST = 100
NODE_RADIUS = 5
NODE_COUNT = 850
SPEED = 4
PLAYBACK_SPEED = 3
BORDER = 30
LINK_FORCE = -0.015

COUPLING = [
    [1, 1, -1],
    [1, 1, 1],
    [1, 1, 1]
]
LINKS = [1, 3, 2]
LINKS_POSSIBLE = [
    [0, 1, 1],
    [1, 2, 1],
    [1, 1, 2]
]
COLORS = [
    (255, 0, 255),    # Красный
    (255, 255, 255),   # Зеленый
    (0, 255, 255)    # Синий
]
BG = (0, 0, 0)  # Черный фон

# Переменные управления
paused = False
selected_particle_type = 0  # Тип частицы для создания (0, 1, 2)
editing_matrix = False  # Режим редактирования матрицы
selected_matrix_i = 0
selected_matrix_j = 0
boundaries_enabled = True  # Включены ли границы экрана

pygame.init()
screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
width, height = screen.get_size()
fw = width // MAX_DIST + 1
fh = height // MAX_DIST + 1

clock = pygame.time.Clock()
font = pygame.font.Font(None, 28)
fps = 0

class LIGHT:
    def __init__(self, size, pixel_shader):
        self.size = size
        self.radius = size * 0.5
        self.render_surface = pygame.Surface((size, size))
        self.pixel_shader_surf = pixel_shader.copy()
        self.baked_pixel_shader_surf = pixel_shader.copy()
        self.render_surface.set_colorkey((0,0,0))

    def main(self, display, x, y):
        self.render_surface.fill((0,0,0))
        self.render_surface.blit(self.pixel_shader_surf, (0, 0))
        display.blit(self.render_surface, (x - self.radius, y - self.radius), special_flags=BLEND_ADD)
        return display

def pixel_shader(size, color, intensity):
    final_array = np.zeros((size, size, 3), dtype=np.float64)
    radius = size * 0.5

    # Создаем сетку координат
    x, y = np.meshgrid(np.arange(size), np.arange(size))
    x = x.astype(np.float64)
    y = y.astype(np.float64)

    # Вычисляем расстояние от центра
    distance = np.sqrt((x - radius)**2 + (y - radius)**2)
    
    # Реалистичное затухание света (обратный квадрат расстояния)
    falloff = np.zeros_like(distance)
    mask = distance > 0
    falloff[mask] = 1.0 / (1 + (distance[mask] / (radius * 0.3))**2)
    
    # Дополнительное мягкое затухание на краях
    edge_falloff = np.maximum(0, (radius - distance) / radius)
    falloff *= edge_falloff
    
    # Применяем интенсивность и цвет
    for i in range(3):
        final_array[:, :, i] = color[i] * falloff * intensity

    return pygame.surfarray.make_surface(final_array.astype(np.uint8))

class Particle:
    def __init__(self, ptype, x, y):
        self.type = ptype
        self.x = x
        self.y = y
        self.sx = 0
        self.sy = 0
        self.links = 0
        self.bonds = []
        # Создаем источник света для частицы
        light_size = NODE_RADIUS * 8
        light_intensity = 1
        self.light = LIGHT(light_size, pixel_shader(light_size, COLORS[ptype], light_intensity))

    @property
    def fx(self):
        return int(self.x // MAX_DIST)
    @property
    def fy(self):
        return int(self.y // MAX_DIST)

class Field:
    def __init__(self):
        self.particles = []

def init_simulation():
    """Инициализация/перезапуск симуляции"""
    global fields, particles, bonds
    
    # Очищаем поля
    fields = [[Field() for _ in range(fh)] for _ in range(fw)]
    particles = []
    bonds = []
    
    # Создаем новые частицы
    for _ in range(NODE_COUNT):
        ptype = random.randint(0, 2)
        x = random.uniform(0, width)
        y = random.uniform(0, height)
        p = Particle(ptype, x, y)
        fields[p.fx][p.fy].particles.append(p)
        particles.append(p)

def clear_screen():
    """Очистка экрана от всех частиц"""
    global fields, particles, bonds
    
    fields = [[Field() for _ in range(fh)] for _ in range(fw)]
    particles = []
    bonds = []

def find_particle_at_position(x, y):
    """Найти частицу в указанной позиции"""
    for p in particles:
        dx = p.x - x
        dy = p.y - y
        if dx*dx + dy*dy <= (NODE_RADIUS * 2)**2:  # Увеличиваем область клика
            return p
    return None

def remove_particle(particle):
    """Удалить частицу и все её связи"""
    global particles, bonds
    
    # Удаляем все связи с этой частицей
    for bond in bonds[:]:
        a, b = bond
        if a is particle or b is particle:
            if a is particle:
                b.links -= 1
                if particle in b.bonds:
                    b.bonds.remove(particle)
            else:
                a.links -= 1
                if particle in a.bonds:
                    a.bonds.remove(particle)
            bonds.remove(bond)
    
    # Удаляем частицу из поля
    try:
        fields[particle.fx][particle.fy].particles.remove(particle)
    except ValueError:
        pass
    
    # Удаляем из общего списка
    if particle in particles:
        particles.remove(particle)

def create_particle(x, y, ptype):
    """Создать новую частицу"""
    # Ограничиваем область создания, чтобы не создавать в строке состояния
    if y > height - 40:
        y = height - 40
    
    p = Particle(ptype, x, y)
    fields[p.fx][p.fy].particles.append(p)
    particles.append(p)

def remove_from_list(lst, item):
    try:
        lst.remove(item)
    except ValueError:
        pass

def apply_force(a, b):
    if a is b:
        return
    
    # Вычисляем расстояние с учетом границ (если они отключены)
    dx = a.x - b.x
    dy = a.y - b.y
    
    if not boundaries_enabled:
        # Для торовой топологии находим кратчайшее расстояние
        # Учитываем переход через границы
        if abs(dx) > width / 2:
            dx = dx - width if dx > 0 else dx + width
        if abs(dy) > (height - 40) / 2:  # Учитываем высоту строки состояния
            dy = dy - (height - 40) if dy > 0 else dy + (height - 40)
    
    d2 = dx * dx + dy * dy
    if d2 > MAX_DIST ** 2:
        return
    dA = COUPLING[a.type][b.type] / d2 if d2 != 0 else 0
    dB = COUPLING[b.type][a.type] / d2 if d2 != 0 else 0
    if a.links < LINKS[a.type] and b.links < LINKS[b.type]:
        if d2 < MAX_DIST ** 2 / 4:
            if b not in a.bonds and a not in b.bonds:
                typeCountA = sum(1 for p in a.bonds if p.type == b.type)
                typeCountB = sum(1 for p in b.bonds if p.type == a.type)
                if typeCountA < LINKS_POSSIBLE[a.type][b.type] and typeCountB < LINKS_POSSIBLE[b.type][a.type]:
                    a.bonds.append(b)
                    b.bonds.append(a)
                    a.links += 1
                    b.links += 1
                    bonds.append((a, b))
    else:
        if b not in a.bonds and a not in b.bonds:
            dA = 1 / d2 if d2 != 0 else 0
            dB = 1 / d2 if d2 != 0 else 0

    angle = meth.atan2(dy, dx)
    if d2 < 1:
        d2 = 1
    if d2 < NODE_RADIUS * NODE_RADIUS * 4:
        dA = 1 / d2
        dB = 1 / d2
    a.sx += meth.cos(angle) * dA * SPEED
    a.sy += meth.sin(angle) * dA * SPEED
    b.sx -= meth.cos(angle) * dB * SPEED
    b.sy -= meth.sin(angle) * dB * SPEED

def logic():
    if paused:
        return
        
    # Движение и границы
    for a in particles:
        a.x += a.sx
        a.y += a.sy
        a.sx *= 0.98
        a.sy *= 0.98
        mag = meth.hypot(a.sx, a.sy)
        if mag > 1:
            a.sx /= mag
            a.sy /= mag
        
        # Обработка границ
        if boundaries_enabled:
            # Обычные границы с отражением
            if a.x < BORDER:
                a.sx += SPEED * 0.05
                if a.x < 0:
                    a.x = -a.x
                    a.sx *= -0.5
            elif a.x > width - BORDER:
                a.sx -= SPEED * 0.05
                if a.x > width:
                    a.x = width * 2 - a.x
                    a.sx *= -0.5
            if a.y < BORDER:
                a.sy += SPEED * 0.05
                if a.y < 0:
                    a.y = -a.y
                    a.sy *= -0.5
            elif a.y > height - BORDER - 40:  # Поднимаем нижнюю границу на высоту строки состояния
                a.sy -= SPEED * 0.05
                if a.y > height - 40:
                    a.y = (height - 40) * 2 - a.y
                    a.sy *= -0.5
        else:
            # Торовые границы - переход через границы
            if a.x < 0:
                a.x = width + a.x
            elif a.x > width:
                a.x = a.x - width
            if a.y < 0:
                a.y = height - 40 + a.y  # Учитываем высоту строки состояния
            elif a.y > height - 40:
                a.y = a.y - (height - 40)

    # Проверка разрывов связей
    for bond in bonds[:]:
        a, b = bond
        
        # Вычисляем расстояние с учетом границ
        dx = a.x - b.x
        dy = a.y - b.y
        
        if not boundaries_enabled:
            # Для торовой топологии находим кратчайшее расстояние
            if abs(dx) > width / 2:
                dx = dx - width if dx > 0 else dx + width
            if abs(dy) > (height - 40) / 2:  # Учитываем высоту строки состояния
                dy = dy - (height - 40) if dy > 0 else dy + (height - 40)
        
        d2 = dx * dx + dy * dy
        
        if d2 > MAX_DIST ** 2 / 4:
            a.links -= 1
            b.links -= 1
            remove_from_list(a.bonds, b)
            remove_from_list(b.bonds, a)
            remove_from_list(bonds, bond)
        elif d2 > NODE_RADIUS ** 2 * 4:
            angle = meth.atan2(dy, dx)
            a.sx += meth.cos(angle) * LINK_FORCE * SPEED
            a.sy += meth.sin(angle) * LINK_FORCE * SPEED
            b.sx -= meth.cos(angle) * LINK_FORCE * SPEED
            b.sy -= meth.sin(angle) * LINK_FORCE * SPEED

    # Перемещение частиц между полями
    for fx in range(fw):
        for fy in range(fh):
            field = fields[fx][fy]
            for a in field.particles[:]:
                if a.fx != fx or a.fy != fy:
                    remove_from_list(field.particles, a)
                    fields[a.fx][a.fy].particles.append(a)

    # Силы между частицами (только в соседних клетках)
    for fx in range(fw):
        for fy in range(fh):
            field = fields[fx][fy]
            for i1, a in enumerate(field.particles):
                for j1 in range(i1+1, len(field.particles)):
                    b = field.particles[j1]
                    apply_force(a, b)
                if fx < fw-1:
                    for b in fields[fx+1][fy].particles:
                        apply_force(a, b)
                if fy < fh-1:
                    for b in fields[fx][fy+1].particles:
                        apply_force(a, b)
                if fx < fw-1 and fy < fh-1:
                    for b in fields[fx+1][fy+1].particles:
                        apply_force(a, b)
                        
                # Дополнительные проверки для торовой топологии
                if not boundaries_enabled:
                    # Взаимодействие с частицами на противоположных краях
                    if fx == 0:  # Левый край
                        for b in fields[fw-1][fy].particles:
                            apply_force(a, b)
                    if fy == 0:  # Верхний край
                        for b in fields[fx][fh-1].particles:
                            apply_force(a, b)
                    if fx == 0 and fy == 0:  # Левый верхний угол
                        for b in fields[fw-1][fh-1].particles:
                            apply_force(a, b)

def draw_ui():
    """Отрисовка интерфейса"""
    # Создаем строку состояния внизу экрана
    status_y = height - 40
    status_height = 40
    
    # Черный фон для строки состояния
    status_bg = pygame.Surface((width, status_height))
    status_bg.fill((0, 0, 0))
    screen.blit(status_bg, (0, status_y))
    
    # Левая часть - управление и статус
    current_x = 10

    # Количество частиц
    count_surface = font.render(f"N:{len(particles)}", True, (200, 200, 200))
    screen.blit(count_surface, (current_x, status_y))
    current_x += count_surface.get_width()
    
    # Разделитель
    sep_surface = font.render(" | ", True, (200, 200, 200))
    screen.blit(sep_surface, (current_x, status_y))
    current_x += sep_surface.get_width()

    pause_surface = font.render("SPC:", True, (200, 200, 200))
    screen.blit(pause_surface, (current_x, status_y))
    current_x += pause_surface.get_width()
    
    # Показать статус паузы цветом
    if paused:
        pause_color = (255, 0, 0)  # Красный
        pause_text = "PAUSED  "
    else:
        pause_color = (0, 255, 0)  # Зеленый  
        pause_text = "RUNNING"
    
    pause_surface = font.render(pause_text, True, pause_color)
    screen.blit(pause_surface, (current_x, status_y))
    current_x += pause_surface.get_width()
    
    # Разделитель
    sep_surface = font.render(" | ", True, (200, 200, 200))
    screen.blit(sep_surface, (current_x, status_y))
    current_x += sep_surface.get_width()
    
    # Показать статус границ цветом
    if boundaries_enabled:
        bounds_color = (255, 0, 0)  # Красный для включенных границ
    else:
        bounds_color = (0, 255, 0)  # Зеленый для выключенных границ

    bounds_surface = font.render("B:", True, (200, 200, 200))
    screen.blit(bounds_surface, (current_x, status_y))
    current_x += bounds_surface.get_width()

    bounds_surface = font.render("BORDERS", True, bounds_color)
    screen.blit(bounds_surface, (current_x, status_y))
    current_x += bounds_surface.get_width()
    
    # Команды
    commands_surface = font.render(" | MOUSE:draw R:reset C:clear M:matrix ESC:exit", True, (200, 200, 200))
    screen.blit(commands_surface, (current_x, status_y))
    current_x += commands_surface.get_width()

    # Выбор типа частицы цветными цифрами
    type_text = " | T:"
    type_surface = font.render(type_text, True, (200, 200, 200))
    screen.blit(type_surface, (current_x, status_y))
    current_x += type_surface.get_width()
    
    for i in range(3):
        color = COLORS[i] if i == selected_particle_type else (100, 100, 100)
        number_surface = font.render(str(i+1), True, color)
        screen.blit(number_surface, (current_x, status_y))
        current_x += number_surface.get_width() + 5

    table_text = "| Matrix: "
    table_surface = font.render(table_text, True, (200, 200, 200))
    screen.blit(table_surface, (current_x, status_y))
    current_x += table_surface.get_width()
    
    # Матрица с цветовой схемой: скобки строки - цвет частицы строки, значения - цвет частицы столбца
    for i in range(3):
        if i > 0:
            comma_surface = font.render(", ", True, COLORS[i-1])
            screen.blit(comma_surface, (current_x, status_y))
            current_x += comma_surface.get_width()
        
        # Скобка строки в цвете частицы строки
        bracket_surface = font.render("[", True, COLORS[i])
        screen.blit(bracket_surface, (current_x, status_y))
        current_x += bracket_surface.get_width()
        
        for j in range(3):
            if j > 0:
                comma_surface = font.render(", ", True, COLORS[j-1])
                screen.blit(comma_surface, (current_x, status_y))
                current_x += comma_surface.get_width()
            
            # Выбираем цвет для текущего значения
            if editing_matrix and selected_matrix_i == i and selected_matrix_j == j:
                color = (255, 255, 0)  # Желтый для редактируемого значения
            else:
                color = COLORS[j]  # Цвет частицы столбца
            
            value_surface = font.render(f"{COUPLING[i][j]:.1f}", True, color)
            screen.blit(value_surface, (current_x, status_y))
            current_x += value_surface.get_width()
        
        # Закрывающая скобка строки в цвете частицы строки
        bracket_surface = font.render("]", True, COLORS[i])
        screen.blit(bracket_surface, (current_x, status_y))
        current_x += bracket_surface.get_width()
    
    count_surface = font.render(f" | FPS:", True, (200, 200, 200))
    screen.blit(count_surface, (current_x, status_y))
    current_x += count_surface.get_width()
    count_surface = font.render(f" {fps:.2f}", True, (150, 150, 150))
    screen.blit(count_surface, (current_x, status_y))

def draw_scene():
    screen.fill(BG)
    
    # Отрисовка света от каждой частицы с аддитивным смешиванием
    for p in particles:
        p.light.main(screen, int(p.x), int(p.y))
    
    # Отрисовка связей между частицами
    for bond in bonds:
        a, b = bond
        
        # Вычисляем позиции для отрисовки с учетом границ
        ax, ay = a.x, a.y
        bx, by = b.x, b.y
        
        # Для торовой топологии находим кратчайший путь для отрисовки
        if not boundaries_enabled:
            dx = bx - ax
            dy = by - ay
            
            # Проверяем, нужно ли рисовать через границы
            if abs(dx) > width / 2:
                if dx > 0:
                    bx -= width
                else:
                    bx += width
            
            if abs(dy) > (height - 40) / 2:  # Учитываем высоту строки состояния
                if dy > 0:
                    by -= (height - 40)
                else:
                    by += (height - 40)
        
        # Цвет линии - смешанный цвет двух частиц
        color_a = COLORS[a.type]
        color_b = COLORS[b.type]
        line_color = (
            (color_a[0] + color_b[0]) // 2,
            (color_a[1] + color_b[1]) // 2,
            (color_a[2] + color_b[2]) // 2
        )
        
        # Рисуем линию между частицами
        pygame.draw.line(screen, line_color, (int(ax), int(ay)), (int(bx), int(by)), 2)
    
    # Отрисовка самих частиц поверх света и связей
    for p in particles:
        pygame.draw.circle(screen, COLORS[p.type], (int(p.x), int(p.y)), NODE_RADIUS)
    
    # Отрисовка интерфейса
    draw_ui()
    
    pygame.display.flip()

def handle_mouse_click(pos):
    """Обработка клика мыши"""
    x, y = pos
    
    # Проверяем, есть ли частица в этой позиции
    particle = find_particle_at_position(x, y)
    
    if particle:
        # Удаляем частицу
        remove_particle(particle)
    else:
        # Создаем новую частицу
        create_particle(x, y, selected_particle_type)

# Инициализация симуляции
init_simulation()

# Основной цикл
last_time = time.time()
while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                pygame.quit()
                sys.exit()
            elif event.key == pygame.K_SPACE:
                paused = not paused
            elif event.key == pygame.K_r:
                init_simulation()
            elif event.key == pygame.K_c:
                clear_screen()
            elif event.key == pygame.K_1:
                selected_particle_type = 0
            elif event.key == pygame.K_2:
                selected_particle_type = 1
            elif event.key == pygame.K_3:
                selected_particle_type = 2
            elif event.key == pygame.K_b:
                boundaries_enabled = not boundaries_enabled
            elif event.key == pygame.K_m:
                editing_matrix = not editing_matrix
            elif editing_matrix:
                if event.key == pygame.K_UP:
                    selected_matrix_i = (selected_matrix_i - 1) % 3
                elif event.key == pygame.K_DOWN:
                    selected_matrix_i = (selected_matrix_i + 1) % 3
                elif event.key == pygame.K_LEFT:
                    selected_matrix_j = (selected_matrix_j - 1) % 3
                elif event.key == pygame.K_RIGHT:
                    selected_matrix_j = (selected_matrix_j + 1) % 3
                elif event.key == pygame.K_PLUS or event.key == pygame.K_EQUALS:
                    COUPLING[selected_matrix_i][selected_matrix_j] += 0.1
                elif event.key == pygame.K_MINUS:
                    COUPLING[selected_matrix_i][selected_matrix_j] -= 0.1
                elif event.key == pygame.K_RETURN:
                    editing_matrix = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # Левая кнопка мыши
                handle_mouse_click(event.pos)

    for _ in range(PLAYBACK_SPEED):
        logic()
    draw_scene()
    clock.tick(60)
    
    current_time = time.time()
    delta = current_time - last_time
    last_time = current_time

    if delta > 0:
        fps = 0.9 * fps + 0.1 / delta 