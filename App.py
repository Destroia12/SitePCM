from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import sqlite3
from datetime import datetime
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta'  # Substitua por uma chave segura
DATABASE = 'carretas.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Permite acessar os dados por nome da coluna
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Tabela de veículos (incluindo campo "empresa")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS veiculos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            frota TEXT,
            placa TEXT UNIQUE,
            eixos INTEGER,
            piso TEXT,
            tipo_carreta TEXT,
            comprimento REAL,
            documento TEXT DEFAULT 'Não',
            empresa TEXT
        )
    ''')
    # Tabela de empresas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj TEXT UNIQUE,
            razao_social TEXT UNIQUE,
            inscricao_estadual TEXT,
            local TEXT,
            numero TEXT,
            telefone TEXT,
            email TEXT
        )
    ''')
    # Tabela de aluguéis
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alugueis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            veiculo_id INTEGER,
            possuidor TEXT,
            local TEXT,
            data_locacao TEXT,
            data_devolucao TEXT,
            status TEXT,
            FOREIGN KEY (veiculo_id) REFERENCES veiculos (id)
        )
    ''')
    # Tabela de usuários
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT UNIQUE,
            senha TEXT,
            role TEXT,
            empresa TEXT
        )
    ''')
    conn.commit()
    # Criação dos usuários master (se não existirem)
    for login_val, empresa in [('JTD', 'JTD'), ('PCM', 'PCM')]:
        cursor.execute("SELECT * FROM usuarios WHERE login = ?", (login_val,))
        if cursor.fetchone() is None:
            senha_hash = generate_password_hash("123")
            cursor.execute("INSERT INTO usuarios (login, senha, role, empresa) VALUES (?, ?, ?, ?)",
                           (login_val, senha_hash, "admin", empresa))
            conn.commit()
    conn.close()

init_db()

# ---------------------- Decorators ----------------------
def login_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash("Você precisa fazer login.", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def admin_required(f):
    def wrapper(*args, **kwargs):
        if 'role' not in session or session['role'] != 'admin':
            flash("Acesso restrito a administradores.", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# ---------------------- Rotas de Autenticação ----------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_input = request.form['login']
        senha_input = request.form['senha']
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE login = ?", (login_input,))
        user = cursor.fetchone()
        conn.close()
        if user and check_password_hash(user['senha'], senha_input):
            session['user_id'] = user['id']
            session['login'] = user['login']
            session['role'] = user['role']
            session['empresa'] = user['empresa']  # Guarda a empresa do usuário na sessão
            flash("Login realizado com sucesso!", "success")
            return redirect(url_for('index'))
        else:
            flash("Credenciais inválidas.", "danger")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash("Você saiu do sistema.", "info")
    return redirect(url_for('login'))

# ---------------------- Tela Principal: Lista de Veículos ----------------------
@app.route('/')
@login_required
def index():
    placa_search = request.args.get('placa', '')
    empresa = session.get('empresa')
    conn = get_db_connection()
    cursor = conn.cursor()
    query = '''
        SELECT v.*, COALESCE(a.status, 'Livre') as status
        FROM veiculos v
        LEFT JOIN alugueis a ON v.id = a.veiculo_id AND a.status = 'Ativo'
        WHERE v.placa LIKE ? AND v.empresa = ?
        ORDER BY v.frota
    '''
    cursor.execute(query, ('%' + placa_search + '%', empresa))
    vehicles = cursor.fetchall()
    conn.close()
    return render_template('index.html', vehicles=vehicles, placa_search=placa_search)

# ---------------------- Rotas de Veículos ----------------------
@app.route('/import_excel', methods=['GET', 'POST'])
def import_excel():
    if request.method == 'POST':
        file = request.files.get('excel_file')
        if not file:
            flash("Nenhum arquivo selecionado!", "danger")
            return redirect(url_for('import_excel'))
        try:
            df = pd.read_excel(file)
            expected_columns = {"Frota", "Placa", "Eixos", "Piso", "Tipo de Carreta", "Comprimento"}
            if not expected_columns.issubset(set(df.columns)):
                flash("Arquivo Excel não possui todas as colunas necessárias!", "danger")
                return redirect(url_for('import_excel'))
            conn = get_db_connection()
            cursor = conn.cursor()
            empresa = session.get('empresa') if 'empresa' in session else ''
            for _, row in df.iterrows():
                try:
                    cursor.execute(
                        "INSERT INTO veiculos (frota, placa, eixos, piso, tipo_carreta, comprimento, documento, empresa) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            row["Frota"],
                            row["Placa"],
                            int(row["Eixos"]),
                            row["Piso"],
                            row["Tipo de Carreta"],
                            float(row["Comprimento"]),
                            row.get("Documento", "Não"),
                            empresa
                        )
                    )
                except Exception as e:
                    pass
            conn.commit()
            conn.close()
            flash("Dados importados com sucesso!", "success")
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Erro ao importar dados: {str(e)}", "danger")
            return redirect(url_for('import_excel'))
    return render_template('import_excel.html')

@app.route('/add_vehicle', methods=['GET', 'POST'])
def add_vehicle():
    if request.method == 'POST':
        frota = request.form['frota']
        placa = request.form['placa']
        eixos = request.form['eixos']
        piso = request.form['piso']
        tipo_carreta = request.form['tipo_carreta']
        comprimento = request.form['comprimento']
        documento = request.form.get('documento', 'Não')
        if not frota or not placa:
            flash('Frota e Placa são obrigatórios!', 'danger')
            return redirect(url_for('add_vehicle'))
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            empresa = session.get('empresa')  # Atribui a empresa do usuário logado
            cursor.execute(
                "INSERT INTO veiculos (frota, placa, eixos, piso, tipo_carreta, comprimento, documento, empresa) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (frota, placa, int(eixos), piso, tipo_carreta, float(comprimento), documento, empresa)
            )
            conn.commit()
            conn.close()
            flash('Veículo cadastrado com sucesso!', 'success')
            return redirect(url_for('index'))
        except sqlite3.IntegrityError:
            flash('Placa já cadastrada!', 'warning')
        except Exception as e:
            flash(f'Erro ao cadastrar veículo: {str(e)}', 'danger')
    return render_template('add_vehicle.html')

@app.route('/edit_vehicle/<int:vehicle_id>', methods=['GET', 'POST'])
def edit_vehicle(vehicle_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM veiculos WHERE id = ?", (vehicle_id,))
    vehicle = cursor.fetchone()
    if not vehicle:
        flash('Veículo não encontrado!', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        frota = request.form['frota']
        placa = request.form['placa']
        eixos = request.form['eixos']
        piso = request.form['piso']
        tipo_carreta = request.form['tipo_carreta']
        comprimento = request.form['comprimento']
        documento = request.form.get('documento', 'Não')
        try:
            cursor.execute('''
                UPDATE veiculos 
                SET frota = ?, placa = ?, eixos = ?, piso = ?, tipo_carreta = ?, comprimento = ?, documento = ?
                WHERE id = ?
            ''', (frota, placa, int(eixos), piso, tipo_carreta, float(comprimento), documento, vehicle_id))
            conn.commit()
            flash('Veículo atualizado com sucesso!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Erro ao atualizar veículo: {str(e)}', 'danger')
    conn.close()
    return render_template('edit_vehicle.html', vehicle=vehicle)

@app.route('/delete_vehicle/<int:vehicle_id>', methods=['POST'])
def delete_vehicle(vehicle_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM alugueis WHERE veiculo_id = ? AND status = 'Ativo'", (vehicle_id,))
    if cursor.fetchone()[0] > 0:
        flash('Não é possível excluir um veículo que está alugado!', 'danger')
        conn.close()
        return redirect(url_for('index'))
    try:
        cursor.execute("DELETE FROM veiculos WHERE id = ?", (vehicle_id,))
        conn.commit()
        flash('Veículo excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir veículo: {str(e)}', 'danger')
    conn.close()
    return redirect(url_for('index'))

@app.route('/rent_vehicle/<int:vehicle_id>', methods=['GET', 'POST'])
def rent_vehicle(vehicle_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM alugueis WHERE veiculo_id = ? AND status = 'Ativo'", (vehicle_id,))
    if cursor.fetchone()[0] > 0:
        flash('Este veículo já está alugado!', 'danger')
        conn.close()
        return redirect(url_for('index'))
    cursor.execute("SELECT frota, placa FROM veiculos WHERE id = ?", (vehicle_id,))
    vehicle = cursor.fetchone()
    if not vehicle:
        flash('Veículo não encontrado!', 'danger')
        conn.close()
        return redirect(url_for('index'))
    cursor.execute("SELECT id, razao_social FROM empresas ORDER BY razao_social")
    companies = cursor.fetchall()
    if request.method == 'POST':
        possuidor = request.form['possuidor']
        local = request.form['local']
        data_locacao = request.form['data_locacao']
        if not possuidor or not local or not data_locacao:
            flash('Todos os campos são obrigatórios!', 'danger')
            return redirect(url_for('rent_vehicle', vehicle_id=vehicle_id))
        try:
            cursor.execute(
                "INSERT INTO alugueis (veiculo_id, possuidor, local, data_locacao, status) VALUES (?, ?, ?, ?, ?)",
                (vehicle_id, possuidor, local, data_locacao, "Ativo")
            )
            conn.commit()
            flash('Veículo alugado com sucesso!', 'success')
            conn.close()
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Erro ao registrar aluguel: {str(e)}', 'danger')
    conn.close()
    return render_template('rent_vehicle.html', vehicle=vehicle, companies=companies)

@app.route('/rentals')
def rentals():
    placa_search = request.args.get('placa', '')
    possuidor_search = request.args.get('possuidor', '')
    empresa = session.get('empresa')
    conn = get_db_connection()
    cursor = conn.cursor()
    query = '''
        SELECT a.*, v.frota, v.placa, a.data_locacao
        FROM alugueis a
        JOIN veiculos v ON a.veiculo_id = v.id
        WHERE a.status = 'Ativo' AND v.empresa = ?
    '''
    params = [empresa]
    if placa_search:
        query += " AND v.placa LIKE ?"
        params.append('%' + placa_search + '%')
    if possuidor_search:
        query += " AND a.possuidor LIKE ?"
        params.append('%' + possuidor_search + '%')
    query += " ORDER BY v.frota"
    cursor.execute(query, params)
    rentals = cursor.fetchall()
    conn.close()
    new_rentals = []
    for rental in rentals:
        rental_dict = dict(rental)
        try:
            rental_date = datetime.strptime(rental_dict['data_locacao'], "%Y-%m-%d")
            dias = (datetime.now() - rental_date).days
        except Exception:
            dias = 0
        rental_dict['dias_uso'] = dias
        new_rentals.append(rental_dict)
    return render_template('rentals.html', rentals=new_rentals, placa_search=placa_search, possuidor_search=possuidor_search)

@app.route('/finish_rental/<int:rental_id>', methods=['POST'])
def finish_rental(rental_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    data_devolucao = datetime.now().strftime("%Y-%m-%d")
    try:
        cursor.execute("UPDATE alugueis SET status = 'Finalizado', data_devolucao = ? WHERE id = ?", (data_devolucao, rental_id))
        conn.commit()
        flash('Aluguel finalizado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao finalizar aluguel: {str(e)}', 'danger')
    conn.close()
    return redirect(url_for('rentals'))

@app.route('/historico')
def historico():
    data_inicial = request.args.get('data_inicial', '')
    data_final = request.args.get('data_final', '')
    empresa = session.get('empresa')
    conn = get_db_connection()
    cursor = conn.cursor()
    query = '''
        SELECT a.*, v.frota, v.placa 
        FROM alugueis a
        JOIN veiculos v ON a.veiculo_id = v.id
        WHERE a.status = 'Finalizado' AND v.empresa = ?
    '''
    params = [empresa]
    if data_inicial and data_final:
        query += " AND a.data_devolucao BETWEEN ? AND ?"
        params.extend([data_inicial, data_final])
    query += " ORDER BY a.data_devolucao DESC"
    cursor.execute(query, params)
    historico = cursor.fetchall()
    conn.close()
    return render_template('historico.html', historico=historico, data_inicial=data_inicial, data_final=data_final)

# ---------------------- Rotas de Gerenciamento de Usuários ----------------------
@app.route('/dashboard')
@login_required
@admin_required
def dashboard():
    empresa = session.get('empresa')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE empresa = ? ORDER BY login", (empresa,))
    users = cursor.fetchall()
    conn.close()
    return render_template('dashboard.html', users=users)

@app.route('/create_user', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    if request.method == 'POST':
        login_new = request.form['login']
        senha_new = request.form['senha']
        role_new = request.form['role']  # "admin" ou "comum"
        empresa_new = session.get('empresa')  # Força a empresa do novo usuário ser a mesma do admin logado
        if not login_new or not senha_new:
            flash("Login e senha são obrigatórios.", "danger")
            return redirect(url_for('create_user'))
        senha_hash = generate_password_hash(senha_new)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO usuarios (login, senha, role, empresa) VALUES (?, ?, ?, ?)",
                           (login_new, senha_hash, role_new, empresa_new))
            conn.commit()
            flash("Usuário criado com sucesso.", "success")
        except Exception as e:
            flash(f"Erro ao criar usuário: {str(e)}", "danger")
        conn.close()
        return redirect(url_for('dashboard'))
    return render_template('create_user.html')


@app.route('/cadastro_empresas', methods=['GET', 'POST'])
@login_required
@admin_required
def cadastro_empresas():
    conn = get_db_connection()
    cursor = conn.cursor()
    if request.method == 'POST':
        cnpj = request.form['cnpj']
        razao_social = request.form['razao_social']
        inscricao_estadual = request.form['inscricao_estadual']
        local = request.form['local']
        numero = request.form['numero']
        telefone = request.form['telefone']
        email = request.form['email']
        try:
            cursor.execute(
                "INSERT INTO empresas (cnpj, razao_social, inscricao_estadual, local, numero, telefone, email) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cnpj, razao_social, inscricao_estadual, local, numero, telefone, email)
            )
            conn.commit()
            flash("Empresa cadastrada com sucesso!", "success")
        except Exception as e:
            flash(f"Erro ao cadastrar empresa: {str(e)}", "danger")
        return redirect(url_for('cadastro_empresas'))
    cursor.execute("SELECT * FROM empresas")
    empresas = cursor.fetchall()
    conn.close()
    return render_template('companies.html', empresas=empresas)


@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for('dashboard'))
    if user['empresa'] != session.get('empresa'):
        flash("Você não tem permissão para editar esse usuário.", "danger")
        conn.close()
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        login_new = request.form['login']
        senha_new = request.form.get('senha', '')
        role_new = request.form['role']
        empresa_new = session.get('empresa')  # A empresa permanece a mesma
        if senha_new:
            senha_hash = generate_password_hash(senha_new)
            cursor.execute("UPDATE usuarios SET login = ?, senha = ?, role = ?, empresa = ? WHERE id = ?",
                           (login_new, senha_hash, role_new, empresa_new, user_id))
        else:
            cursor.execute("UPDATE usuarios SET login = ?, role = ?, empresa = ? WHERE id = ?",
                           (login_new, role_new, empresa_new, user_id))
        conn.commit()
        flash("Usuário atualizado com sucesso.", "success")
        conn.close()
        return redirect(url_for('dashboard'))
    conn.close()
    return render_template('edit_user.html', user=user)

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == session.get('user_id'):
        flash("Você não pode excluir seu próprio usuário.", "danger")
        return redirect(url_for('dashboard'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user or user['empresa'] != session.get('empresa'):
        flash("Você não tem permissão para excluir esse usuário.", "danger")
        conn.close()
        return redirect(url_for('dashboard'))
    cursor.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash("Usuário excluído com sucesso.", "success")
    return redirect(url_for('dashboard'))

@app.route('/meu_perfil', methods=['GET', 'POST'])
@login_required
@admin_required
def meu_perfil():
    user_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if request.method == 'POST':
        login_new = request.form['login']
        senha_new = request.form.get('senha', '')
        if senha_new:
            senha_hash = generate_password_hash(senha_new)
            cursor.execute("UPDATE usuarios SET login = ?, senha = ? WHERE id = ?", (login_new, senha_hash, user_id))
        else:
            cursor.execute("UPDATE usuarios SET login = ? WHERE id = ?", (login_new, user_id))
        conn.commit()
        conn.close()
        session['login'] = login_new
        flash("Perfil atualizado com sucesso.", "success")
        return redirect(url_for('dashboard'))
    conn.close()
    return render_template('meu_perfil.html', user=user)

# ---------------------- Exportação para Excel ----------------------
@app.route('/export_excel/<string:tipo>')
def export_excel(tipo):
    conn = get_db_connection()
    cursor = conn.cursor()
    if tipo == 'veiculos':
        cursor.execute("SELECT frota, placa, eixos, piso, tipo_carreta, comprimento FROM veiculos ORDER BY frota")
        data = cursor.fetchall()
        columns = ["Frota", "Placa", "Eixos", "Piso", "Tipo de Carreta", "Comprimento"]
    elif tipo == 'alugados':
        cursor.execute('''
            SELECT v.frota, v.placa, v.eixos, v.piso, v.tipo_carreta, v.comprimento,
                   a.possuidor, a.local, a.data_locacao, a.data_devolucao
            FROM alugueis a
            JOIN veiculos v ON a.veiculo_id = v.id
            WHERE a.status = 'Ativo'
            ORDER BY v.frota
        ''')
        data = cursor.fetchall()
        columns = ["Frota", "Placa", "Eixos", "Piso", "Tipo de Carreta", "Comprimento",
                   "Possuidor", "Local", "Data Locação", "Data Devolução"]
    elif tipo == 'historico':
        cursor.execute('''
            SELECT v.frota, v.placa, v.eixos, v.piso, v.tipo_carreta, v.comprimento,
                   a.possuidor, a.local, a.data_locacao, a.data_devolucao
            FROM alugueis a
            JOIN veiculos v ON a.veiculo_id = v.id
            WHERE a.status = 'Finalizado'
            ORDER BY a.data_devolucao DESC
        ''')
        data = cursor.fetchall()
        columns = ["Frota", "Placa", "Eixos", "Piso", "Tipo de Carreta", "Comprimento",
                   "Possuidor", "Local", "Data Locação", "Data Devolução"]
    else:
        flash("Tipo de exportação inválido", 'danger')
        conn.close()
        return redirect(url_for('index'))
    df = pd.DataFrame(data, columns=columns)
    filename = f"{tipo}.xlsx"
    df.to_excel(filename, index=False)
    conn.close()
    return send_file(filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
