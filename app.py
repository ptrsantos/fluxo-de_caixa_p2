import io
import time
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from xhtml2pdf import pisa
#from flask_wtf.csrf import CSRFProtect#<---
# Import the category form
from forms import CategoriaForm

# App configuration
app = Flask(__name__)
app.config['SECRET_KEY'] = 'chave-secreta-do-aplicativo'  # Consider using environment variable
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:@localhost/fluxo_de_caixa'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# csrf = CSRFProtect(app)  #<---

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Make datetime available in all templates
@app.context_processor
def inject_now():
    return {'now': datetime.now}

# Database models
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    senha_hash = db.Column(db.String(200), nullable=False)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    transacoes = db.relationship('Transacao', backref='usuario', lazy=True, cascade="all, delete-orphan")

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)
    
    def verificar_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # 'entrada' ou 'saida'
    transacoes = db.relationship('Transacao', backref='categoria', lazy=True)
    
    def __repr__(self):
        return f"<Categoria {self.nome}>"

class Transacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # 'entrada' ou 'saida'
    data = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    
    def __repr__(self):
        return f"<Transacao {self.descricao}: R${self.valor}>"

@login_manager.user_loader
def carregar_usuario(id):
    return Usuario.query.get(int(id))

# Utility functions
def format_currency(value):
    """Format float as Brazilian currency"""
    return f"R$ {value:.2f}"

# Custom decorators
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Implement admin check logic here if needed
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        # Check if user already exists
        usuario_existente = Usuario.query.filter_by(email=email).first()
        if usuario_existente:
            flash('Email já registrado. Faça login.', 'warning')
            return redirect(url_for('login'))
        
        # Create new user
        novo_usuario = Usuario(nome=nome, email=email)
        novo_usuario.set_senha(senha)
        
        try:
            db.session.add(novo_usuario)
            db.session.commit()
            flash('Conta criada com sucesso! Faça login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao criar conta: {str(e)}', 'danger')
    
    return render_template('registrar.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        usuario = Usuario.query.filter_by(email=email).first()
        
        if usuario and usuario.verificar_senha(senha):
            login_user(usuario)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Email ou senha inválidos.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get current month's transactions
    hoje = datetime.now()
    primeiro_dia = datetime(hoje.year, hoje.month, 1)
    
    transacoes = Transacao.query.filter_by(usuario_id=current_user.id).filter(
        Transacao.data >= primeiro_dia
    ).order_by(Transacao.data.desc()).all()
    
    # Calculate balance
    total_entradas = sum(t.valor for t in transacoes if t.tipo == 'entrada')
    total_saidas = sum(t.valor for t in transacoes if t.tipo == 'saida')
    saldo = total_entradas - total_saidas
    
    return render_template('dashboard.html', 
                          transacoes=transacoes, 
                          saldo=saldo,
                          total_entradas=total_entradas,
                          total_saidas=total_saidas)

@app.route('/adicionar_transacao', methods=['GET', 'POST'])
@login_required
def adicionar_transacao():
    categorias = Categoria.query.all()
    
    if request.method == 'POST':
        try:
            descricao = request.form.get('descricao')
            valor = float(request.form.get('valor'))
            tipo = request.form.get('tipo')
            data_str = request.form.get('data')
            categoria_id = request.form.get('categoria_id') or None
            
            # Convert date string to datetime object
            data = datetime.strptime(data_str, '%Y-%m-%d')
            
            # Create new transaction
            nova_transacao = Transacao(
                descricao=descricao,
                valor=valor,
                tipo=tipo,
                data=data,
                categoria_id=categoria_id,
                usuario_id=current_user.id
            )
            
            db.session.add(nova_transacao)
            db.session.commit()
            
            flash('Transação adicionada com sucesso!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao adicionar transação: {str(e)}', 'danger')
    
    return render_template('adicionar_transacao.html', categorias=categorias)

@app.route('/editar_transacao/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_transacao(id):
    transacao = Transacao.query.get_or_404(id)
    
    # Ensure user can only edit their own transactions
    if transacao.usuario_id != current_user.id:
        flash('Você não tem permissão para editar esta transação.', 'danger')
        return redirect(url_for('dashboard'))
    
    categorias = Categoria.query.all()
    
    if request.method == 'POST':
        try:
            transacao.descricao = request.form.get('descricao')
            transacao.valor = float(request.form.get('valor'))
            transacao.tipo = request.form.get('tipo')
            transacao.data = datetime.strptime(request.form.get('data'), '%Y-%m-%d')
            transacao.categoria_id = request.form.get('categoria_id') or None
            
            db.session.commit()
            flash('Transação atualizada com sucesso!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar transação: {str(e)}', 'danger')
    
    return render_template('editar_transacao.html', transacao=transacao, categorias=categorias)

@app.route('/excluir_transacao/<int:id>', methods=['POST'])
@login_required
def excluir_transacao(id):
    transacao = Transacao.query.get_or_404(id)
    
    # Ensure user can only delete their own transactions
    if transacao.usuario_id != current_user.id:
        flash('Você não tem permissão para excluir esta transação.', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        db.session.delete(transacao)
        db.session.commit()
        flash('Transação excluída com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao excluir transação: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/categorias')
@login_required
def categorias():
    todas_categorias = Categoria.query.all()
    return render_template('categorias.html', categorias=todas_categorias)

@app.route('/adicionar_categoria', methods=['GET', 'POST'])
@login_required
def adicionar_categoria():
    form = CategoriaForm()
    
    if form.validate_on_submit():
        try:
            nova_categoria = Categoria(nome=form.nome.data, tipo=form.tipo.data)
            db.session.add(nova_categoria)
            db.session.commit()
            flash('Categoria adicionada com sucesso!', 'success')
            return redirect(url_for('categorias'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao adicionar categoria: {str(e)}', 'danger')
    
    return render_template('adicionar_categoria.html', form=form)

@app.route('/editar_categoria/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_categoria(id):
    categoria = Categoria.query.get_or_404(id)
    form = CategoriaForm(obj=categoria)
    
    if form.validate_on_submit():
        try:
            categoria.nome = form.nome.data
            categoria.tipo = form.tipo.data
            db.session.commit()
            flash('Categoria atualizada com sucesso!', 'success')
            return redirect(url_for('categorias'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao atualizar categoria: {str(e)}', 'danger')
    
    return render_template('editar_categoria.html', form=form, categoria=categoria)

@app.route('/relatorios', methods=['GET'])
@login_required
def relatorios():
    # Get date parameters from form
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')

    # Check if dates were provided
    if not data_inicio or not data_fim:
        # Set default to current month if no dates provided
        hoje = datetime.now()
        data_inicio = datetime(hoje.year, hoje.month, 1).strftime('%Y-%m-%d')
        data_fim = hoje.strftime('%Y-%m-%d')
        
        return render_template('relatorios.html', 
                              data_inicio=data_inicio,
                              data_fim=data_fim,
                              receitas_totais=0, 
                              despesas_totais=0, 
                              saldo_final=0, 
                              detalhes=[])

    # Convert date strings to datetime objects
    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d')
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d')

    # Filter transactions in date range
    transacoes = Transacao.query.filter_by(usuario_id=current_user.id).filter(
        Transacao.data >= data_inicio_dt,
        Transacao.data <= data_fim_dt
    ).order_by(Transacao.data.desc()).all()

    # Calculate totals
    receitas_totais = sum(t.valor for t in transacoes if t.tipo == 'entrada')
    despesas_totais = sum(t.valor for t in transacoes if t.tipo == 'saida')
    saldo_final = receitas_totais - despesas_totais

    # Group by category for analytics
    categorias_receitas = {}
    categorias_despesas = {}
    
    for t in transacoes:
        cat_nome = t.categoria.nome if t.categoria else "Sem Categoria"
        if t.tipo == 'entrada':
            categorias_receitas[cat_nome] = categorias_receitas.get(cat_nome, 0) + t.valor
        else:
            categorias_despesas[cat_nome] = categorias_despesas.get(cat_nome, 0) + t.valor

    # Render template with report data
    return render_template('relatorios.html',
                          data_inicio=data_inicio,
                          data_fim=data_fim,
                          receitas_totais=receitas_totais,
                          despesas_totais=despesas_totais,
                          saldo_final=saldo_final,
                          categorias_receitas=categorias_receitas,
                          categorias_despesas=categorias_despesas,
                          detalhes=transacoes)

@app.route('/relatorios/pdf')
@login_required
def relatorios_pdf():
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')

    if not data_inicio or not data_fim:
        flash('Por favor, selecione um intervalo de datas.', 'warning')
        return redirect(url_for('relatorios'))

    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d')
    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d')

    transacoes = Transacao.query.filter_by(usuario_id=current_user.id).filter(
        Transacao.data >= data_inicio_dt,
        Transacao.data <= data_fim_dt
    ).order_by(Transacao.data).all()

    receitas_totais = sum(t.valor for t in transacoes if t.tipo == 'entrada')
    despesas_totais = sum(t.valor for t in transacoes if t.tipo == 'saida')
    saldo_final = receitas_totais - despesas_totais

    # Group by category
    categorias_receitas = {}
    categorias_despesas = {}
    
    for t in transacoes:
        cat_nome = t.categoria.nome if t.categoria else "Sem Categoria"
        if t.tipo == 'entrada':
            categorias_receitas[cat_nome] = categorias_receitas.get(cat_nome, 0) + t.valor
        else:
            categorias_despesas[cat_nome] = categorias_despesas.get(cat_nome, 0) + t.valor

    # Create summary dictionary
    resumo = {
        'data_inicio': data_inicio_dt.strftime('%d/%m/%Y'),
        'data_fim': data_fim_dt.strftime('%d/%m/%Y'),
        'receitas_totais': format_currency(receitas_totais),
        'despesas_totais': format_currency(despesas_totais),
        'saldo_final': format_currency(saldo_final),
        'categorias_receitas': {k: format_currency(v) for k, v in categorias_receitas.items()},
        'categorias_despesas': {k: format_currency(v) for k, v in categorias_despesas.items()}
    }

    # Render HTML template for PDF
    html = render_template(
        'relatorios_pdf.html',
        usuario=current_user,
        resumo=resumo,
        detalhes=transacoes
    )

    # Generate PDF from HTML
    result = io.BytesIO()
    pdf = pisa.CreatePDF(html, dest=result)
    
    if pdf.err:
        flash('Erro ao gerar PDF', 'danger')
        return redirect(url_for('relatorios'))

    # Prepare response with PDF content
    response = make_response(result.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="relatorio_{data_inicio}_a_{data_fim}.pdf"'
    return response

# Create default categories
def inicializar_categorias():
    if Categoria.query.first() is None:
        categorias_padrao = [
            ('Salário', 'entrada'),
            ('Vendas', 'entrada'),
            ('Investimentos', 'entrada'),
            ('Outros', 'entrada'),
            ('Alimentação', 'saida'),
            ('Moradia', 'saida'),
            ('Transporte', 'saida'),
            ('Entretenimento', 'saida'),
            ('Saúde', 'saida'),
            ('Educação', 'saida'),
            ('Despesas Gerais', 'saida')
        ]
        
        for nome, tipo in categorias_padrao:
            categoria = Categoria(nome=nome, tipo=tipo)
            db.session.add(categoria)
        
        try:
            db.session.commit()
            print("Categorias padrão criadas com sucesso!")
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao criar categorias padrão: {str(e)}")

# Error handlers
@app.errorhandler(404)
def pagina_nao_encontrada(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def erro_interno(e):
    db.session.rollback()  # Rollback any failed transaction
    return render_template('500.html'), 500

# CLI commands for database management
@app.cli.command("init-db")
def init_db_command():
    """Clear and initialize the database."""
    with app.app_context():
        db.create_all()
        inicializar_categorias()
        print("Database initialized!")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        inicializar_categorias()
    app.run(debug=True)