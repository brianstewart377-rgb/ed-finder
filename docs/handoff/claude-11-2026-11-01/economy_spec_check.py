"""Independent check of the S5a spec's test numbers (hundredths arithmetic)."""
import sys
from collections import defaultdict

sys.path.insert(0, sys.argv[1] + '/apps/api/src')
from cpe.catalogue import planner_facilities  # noqa: E402

CAT = planner_facilities()
STARS = {'black_hole', 'neutron_star', 'white_dwarf', 'brown_dwarf', 'other_star'}
BASE = {'black_hole': ['HighTech', 'Tourism'], 'neutron_star': ['HighTech', 'Tourism'], 'white_dwarf': ['HighTech', 'Tourism'],
        'brown_dwarf': ['Military'], 'other_star': ['Military'], 'earth_like_world': ['Agriculture', 'HighTech', 'Military', 'Tourism'],
        'water_world': ['Agriculture', 'Tourism'], 'ammonia_world': ['HighTech', 'Tourism'], 'gas_giant': ['HighTech', 'Industrial'],
        'high_metal_content_world': ['Extraction'], 'metal_rich_body': ['Extraction'], 'rocky_ice_body': ['Industrial', 'Refinery'],
        'rocky_body': ['Refinery'], 'icy_body': ['Industrial']}
NO_SIG = {'earth_like_world', 'water_world', 'ammonia_world', 'gas_giant'}
TIER = {1: 40, 2: 80, 3: 120}


def B(ref, kind, parent=None, tl=False, volc=False, tf=False, rings=False, geo=0, bio=0):
    return dict(ref=ref, kind=kind, parent=parent, tl=tl, volc=volc, tf=tf, rings=rings, geo=geo, bio=bio)


def S(sid, fid, body, status='complete', slot=None):
    if slot is None:
        slot = 'surface' if 'surface' in CAT[fid].allowed_location else 'orbital'
    return dict(id=sid, fid=fid, body=body, status=status, slot=slot)


def mods(econ, b, bodies, sysf, slot):
    k = b['kind']
    geo = b['geo'] if k not in NO_SIG else 0
    bio = b['bio'] if k not in NO_SIG else 0
    rich = sysf.get('reserve') in ('pristine', 'major')
    poor = sysf.get('reserve') in ('low', 'depleted')
    parent = bodies.get(b['parent'])
    out = []
    if econ == 'Agriculture':
        if k == 'earth_like_world': out.append(('orbiting_earth_like_world', 40))
        if k == 'water_world': out.append(('orbiting_water_world', 40))
        if bio: out.append(('on_or_orbiting_body_with_organics', 40))
        if k == 'icy_body': out.append(('on_or_orbiting_icy_body', -40))
        if b['tl'] and parent and parent['kind'] in STARS: out.append(('on_or_orbiting_planet_tidally_locked_to_star', -40))
        if b['tl'] and parent and parent['kind'] not in STARS and parent['tl']:
            gp = bodies.get(parent['parent'])
            if gp and gp['kind'] in STARS:
                out.append(('orbiting_moon_tidally_locked_to_planet_tidally_locked_to_star' if slot == 'orbital'
                            else 'on_moon_tidally_locked_to_planet_tidally_locked_to_star', -40))
    elif econ == 'Extraction':
        if rich: out.append(('system_major_or_pristine_resources', 40))
        if b['volc']: out.append(('on_or_orbiting_body_with_volcanism', 40))
        if poor: out.append(('system_low_or_depleted_resources', -40))
    elif econ == 'HighTech':
        for kk in ('ammonia_world', 'earth_like_world', 'water_world'):
            if k == kk: out.append(('orbiting_' + kk, 40))
        if geo: out.append(('geo', 40))
        if bio: out.append(('bio', 40))
    elif econ in ('Industrial', 'Refinery'):
        if rich: out.append(('rich', 40))
        if poor: out.append(('poor', -40))
    elif econ == 'Tourism':
        for kk in ('ammonia_world', 'earth_like_world', 'water_world'):
            if k == kk: out.append(('orbiting_' + kk, 40))
        for f in ('bh', 'wd', 'ns'):
            if sysf.get(f): out.append((f, 40))
        if geo: out.append(('geo', 40))
        if bio: out.append(('bio', 40))
    return out


def own(site, bodies, sysf):
    t = CAT[site['fid']]
    b = bodies[site['body']]
    if not t.is_colony_port:
        base = 50 if site['fid'] in ('surface_planetary_port_outpost_industrial', 'surface_planetary_port_outpost_scientific') else 100
        return {t.economy: base}
    k = b['kind']
    econs = set(BASE[k])
    geo = b['geo'] if k not in NO_SIG else 0
    bio = b['bio'] if k not in NO_SIG else 0
    if b['rings']: econs.add('Extraction')
    if bio: econs |= {'Agriculture', 'Terraforming'}
    if geo: econs |= {'Extraction', 'Industrial'}
    return {e: max(10, 100 + sum(d for _, d in mods(e, b, bodies, sysf, site['slot']))) for e in econs}


def link(econ, tier, b, bodies, sysf, slot):
    return max(10, TIER[tier] + sum(d for _, d in mods(econ, b, bodies, sysf, slot)))


def evaluate(sites, bodylist, sysf, view='now'):
    bodies = {b['ref']: b for b in bodylist}
    live = [s for s in sites if s['status'] != 'demolished' and (view == 'after_plan' or s['status'] == 'complete')]
    order = {s['id']: i for i, s in enumerate(sites)}
    roles, supports = {}, {}
    by_body = defaultdict(list)
    for s in live:
        by_body[s['body']].append(s)

    def best(ports):
        return sorted(ports, key=lambda s: (-CAT[s['fid']].tier, order[s['id']]))[0]

    receivers = {}
    for body, ss in by_body.items():
        ports = [s for s in ss if CAT[s['fid']].is_port]
        orb = [s for s in ports if s['slot'] == 'orbital']
        sur = [s for s in ports if s['slot'] == 'surface']
        if orb and sur:
            m, r = best(orb), best(sur)
            roles[m['id']] = 'main'; roles[r['id']] = 'remaining_planetary'
            receivers[body] = (m, r)
            for s in orb:
                if s is not m: roles[s['id']] = 'converted'; supports[s['id']] = m['id']
            for s in sur:
                if s is not r: roles[s['id']] = 'converted'; supports[s['id']] = r['id']
        elif ports:
            m = best(ports)
            roles[m['id']] = 'main'
            receivers[body] = (m, None)
            for s in ports:
                if s is not m: roles[s['id']] = 'converted'; supports[s['id']] = m['id']
    econ = defaultdict(lambda: defaultdict(int))
    for s in live:
        if roles.get(s['id']) in ('main', 'remaining_planetary'):
            for e, v in own(s, bodies, sysf).items():
                econ[s['id']][e] += v

    def sends(s):
        t = CAT[s['fid']]
        if roles.get(s['id']) == 'converted':
            return list(own(s, bodies, sysf))
        if t.is_port:
            return []
        return [t.economy] if t.economy else []

    for body, ss in by_body.items():
        if body not in receivers: continue
        m, r = receivers[body]
        b = bodies[body]
        for s in ss:
            if roles.get(s['id']) in ('main', 'remaining_planetary'): continue
            for e in sends(s):
                v = link(e, CAT[s['fid']].tier, b, bodies, sysf, s['slot'])
                if r is not None and s['slot'] == 'surface':
                    econ[r['id']][e] += v
                    econ[m['id']][e] += v
                else:
                    econ[m['id']][e] += v
        if r is not None:
            for e in own(r, bodies, sysf):
                econ[m['id']][e] += link(e, CAT[r['fid']].tier, b, bodies, sysf, r['slot'])
    for s in live:
        if roles.get(s['id']) in ('main', 'remaining_planetary'): continue
        for e in sends(s):
            for body, (m, r) in receivers.items():
                if body == s['body']: continue
                for p in (m, r):
                    if p is not None: econ[p['id']][e] += 5
    return {pid: {e: v / 100 for e, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))} for pid, d in econ.items()}, roles, supports


def check(name, got, want):
    ok = got == want
    print(('OK  ' if ok else 'FAIL'), name, got if not ok else '', '' if ok else f'want {want}')


def others(spec):
    eco_fid = {'Extraction': 'orbital_installation_mining_outpost', 'Industrial': 'surface_settlement_industrial_t1_s',
               'HighTech': 'orbital_installation_relay_station', 'Military': 'orbital_installation_military',
               'Refinery': 'refinery', 'Agriculture': 'surface_settlement_agriculture_t1_s', 'Tourism': 'tourism_installation'}
    out = []
    for e, n in spec.items():
        for i in range(n):
            out.append(S(f'w-{e}-{i}', eco_fid[e], 'OTHER'))
    return out


OTHER = B('OTHER', 'rocky_body', parent='STAR')
STAR = B('STAR', 'other_star')
P = {'reserve': 'pristine'}

r, _, _ = evaluate([S('p', 'dodecahedron_t3', 'X')], [B('X', 'high_metal_content_world')], P); check('Macbeth', r['p'], {'Extraction': 1.4})
r, _, _ = evaluate([S('p', 'orbital_outpost_civilian', 'X')], [B('X', 'high_metal_content_world', volc=True)], P); check('Pordenone', r['p'], {'Extraction': 1.8})
r, _, _ = evaluate([S('p', 'coriolis_station', 'X')], [B('X', 'rocky_body', volc=True)], P); check('Cabral', r['p'], {'Refinery': 1.4})
r, _, _ = evaluate([S('p', 'orbital_outpost_civilian', 'X')], [B('X', 'water_world', volc=True)], {'reserve': 'common'}); check('Heyerdahl', r['p'], {'Agriculture': 1.4, 'Tourism': 1.4})
r, _, _ = evaluate([S('p', 'orbital_outpost_civilian', 'X')], [STAR, B('X', 'water_world', parent='STAR', tl=True, tf=True)], P); check('Simak', r['p'], {'Tourism': 1.4, 'Agriculture': 1.0})
r, _, _ = evaluate([S('p', 'orbital_outpost_civilian', 'X')], [B('X', 'high_metal_content_world', rings=True, geo=2)], P); check('RB-0014', r['p'], {'Extraction': 1.4, 'Industrial': 1.4})
r, _, _ = evaluate([S('p', 'orbis_t3', 'X')] + others({'Tourism': 2, 'Military': 2, 'HighTech': 1}), [STAR, OTHER, B('X', 'water_world')], {'reserve': None})
check('Low Town', r['p'], {'Tourism': 1.5, 'Agriculture': 1.4, 'Military': 0.1, 'HighTech': 0.05})
r, _, _ = evaluate([S('p', 'coriolis_station', 'X'), S('f', 'surface_settlement_industrial_t1_s', 'X')],
                   [STAR, B('GG', 'gas_giant', parent='STAR'), B('X', 'icy_body', parent='GG', tl=True, geo=2, volc=True)], P)
check('Vasellini', r['p'], {'Industrial': 2.2, 'Extraction': 1.8})
r, _, _ = evaluate([S('p', 'orbital_outpost_civilian', 'X')], [B('X', 'icy_body', bio=1)], {'reserve': 'major'}); check('Coblentz', r['p'], {'Industrial': 1.4, 'Agriculture': 1.0, 'Terraforming': 1.0})

pe_bodies = [STAR, OTHER, B('P7', 'water_world', parent='STAR', tl=True), B('P8', 'water_world', parent='STAR', tl=True)]
pe = [S('c', 'coriolis_station', 'P7'), S('o', 'ocellus_station', 'P8'), S('f7', 'orbital_installation_space_farm', 'P7'),
      S('f8', 'orbital_installation_space_farm', 'P8')] + others({'Agriculture': 2, 'Military': 1, 'Extraction': 1})
r, _, _ = evaluate(pe, pe_bodies, P)
want = {'Agriculture': 1.55, 'Tourism': 1.4, 'Extraction': 0.05, 'Military': 0.05}
check('Praea c', r['c'], want); check('Praea o', r['o'], want)
pe2 = [dict(s, status='demolished') if s['id'] in ('f7', 'f8') else s for s in pe]
r, _, _ = evaluate(pe2, pe_bodies, P)
check('Praea after c', r['c']['Agriculture'], 1.1); check('Praea after o', r['o']['Agriculture'], 1.1)

wr_bodies = [STAR, OTHER, B('A5', 'high_metal_content_world', parent='STAR', tl=True, volc=True, geo=3)]
wr = [S('d', 'dodecahedron_t3', 'A5'), S('pp', 'planetary_port', 'A5'), S('m', 'orbital_installation_mining_outpost', 'A5'),
      S('sec', 'orbital_installation_security_station', 'A5'), S('gov', 'orbital_installation_government', 'A5'),
      S('ex', 'surface_settlement_extraction_t2_l', 'A5'), S('r1', 'refinery', 'A5'), S('r2', 'refinery', 'A5'), S('r3', 'refinery', 'A5')]
wr += others({'Extraction': 7, 'Industrial': 3, 'HighTech': 5, 'Military': 4, 'Refinery': 1, 'Agriculture': 1})
r, roles, _ = evaluate(wr, wr_bodies, P)
check('Wregoe Dodec', r['d'], {'Extraction': 6.95, 'Refinery': 3.65, 'Industrial': 3.15, 'Military': 1.0, 'HighTech': 0.25, 'Agriculture': 0.05})
check('Wregoe PP', r['pp'], {'Extraction': 3.75, 'Refinery': 3.65, 'Industrial': 1.55, 'HighTech': 0.25, 'Military': 0.2, 'Agriculture': 0.05})
check('Wregoe roles', (roles['d'], roles['pp']), ('main', 'remaining_planetary'))

r, roles, sup = evaluate([S('a', 'coriolis_station', 'X'), S('b', 'surface_planetary_port_outpost_civilian', 'X'), S('c', 'planetary_port', 'X')],
                         [B('X', 'rocky_body')], P)
check('Roles dual', (roles['a'], roles['c'], roles['b'], sup['b']), ('main', 'remaining_planetary', 'converted', 'c'))
print('dual roles result', r)
r, roles, sup = evaluate([S('a', 'coriolis_station', 'X'), S('b', 'orbis_t3', 'X')], [B('X', 'rocky_body')], P)
check('Higher tier wins', (roles['b'], roles['a'], sup['a']), ('main', 'converted', 'b'))
