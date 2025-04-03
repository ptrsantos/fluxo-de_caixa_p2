import io
from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
from xhtml2pdf import pisa  # Importar pisa para geração de PDFs
import time

# Importando o formulário de categoria
from forms import CategoriaForm

# Configuração do aplicativo
app = Flask(__name__)
app.config['SECRET_KEY'] = 'chave-secreta-do-aplicativo'
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fluxo_caixa.db'
# app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:@localhost/fluxo_de_caixa?ssl=true'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:@localhost/fluxo_de_caixa'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

@app.context_processor
def inject_now():
    return {'now': datetime.now}

# Inicialização do banco de dados
db = SQLAlchemy(app)

# Inicializar o Flask-Migrate
migrate = Migrate(app, db)

# Configuração do gerenciador de login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Modelos de dados
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    senha_hash = db.Column(db.String(200), nullable=False)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    transacoes = db.relationship('Transacao', backref='usuario', lazy=True)

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)
    
    def verificar_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # 'entrada' ou 'saida'
    transacoes = db.relationship('Transacao', backref='categoria', lazy=True)

class Transacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # 'entrada' ou 'saida'
    data = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

@login_manager.user_loader
def carregar_usuario(id):
    return Usuario.query.get(int(id))

# Rotas da aplicação
@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        # Verificar se o usuário já existe
        usuario_existente = Usuario.query.filter_by(email=email).first()
        if usuario_existente:
            flash('Email já registrado. Faça login.')
            return redirect(url_for('login'))
        
        # Criar novo usuário
        novo_usuario = Usuario(nome=nome, email=email)
        novo_usuario.set_senha(senha)
        
        # Adicionar ao banco de dados
        db.session.add(novo_usuario)
        db.session.commit()
        
        flash('Conta criada com sucesso! Faça login.')
        return redirect(url_for('login'))
    
    return render_template('registrar.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    time.sleep(0.12)
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        usuario = Usuario.query.filter_by(email=email).first()
        
        if usuario and usuario.verificar_senha(senha):
            login_user(usuario)
            return redirect(url_for('dashboard'))
        else:
            flash('Email ou senha inválidos.')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Obter transações do mês atual
    agora = datetime.utcnow()
    primeiro_dia = datetime(agora.year, agora.month, 1)
    
    transacoes = Transacao.query.filter_by(usuario_id=current_user.id).filter(
        Transacao.data >= primeiro_dia
    ).order_by(Transacao.data.desc()).all()
    
    # Calcular saldo
    total_entradas = sum(t.valor for t in transacoes if t.tipo == 'entrada')
    total_saidas = sum(t.valor for t in transacoes if t.tipo == 'saida')
    saldo = total_entradas - total_saidas
    
    time.sleep(0.12)
    return render_template('dashboard.html', 
                          transacoes=transacoes, 
                          saldo=saldo,
                          total_entradas=total_entradas,
                          total_saidas=total_saidas)

@app.route('/adicionar_transacao', methods=['GET', 'POST'])
@login_required
def adicionar_transacao():
    if request.method == 'POST':
        descricao = request.form.get('descricao')
        valor = float(request.form.get('valor'))
        tipo = request.form.get('tipo')
        data_str = request.form.get('data')
        categoria_id = request.form.get('categoria_id')
        
        # Converter string de data para objeto datetime
        data = datetime.strptime(data_str, '%Y-%m-%d')
        
        # Criar nova transação
        nova_transacao = Transacao(
            descricao=descricao,
            valor=valor,
            tipo=tipo,
            data=data,
            categoria_id=categoria_id if categoria_id else None,
            usuario_id=current_user.id
        )
        
        # Adicionar ao banco de dados
        db.session.add(nova_transacao)
        db.session.commit()
        
        flash('Transação adicionada com sucesso!')
        return redirect(url_for('dashboard'))
    
    categorias = Categoria.query.all()
    return render_template('adicionar_transacao.html', categorias=categorias)

@app.route('/categorias')
@login_required
def categorias():
    todas_categorias = Categoria.query.all()
    return render_template('categorias.html', categorias=todas_categorias)

@app.route('/adicionar_categoria', methods=['GET', 'POST'])
@login_required
def adicionar_categoria():
    form = CategoriaForm()
    #if form.validate_on_submit():
    #if request.method == 'POST':
    if form.validate_on_submit() and request.method == 'POST':
        nova_categoria = Categoria(nome=form.nome.data, tipo=form.tipo.data)
        db.session.add(nova_categoria)
        db.session.commit()
        flash('Categoria adicionada com sucesso!')
        return redirect(url_for('categorias'))
    return render_template('adicionar_categoria.html', form=form)

@app.route('/relatorios', methods=['GET'])
@login_required
def relatorios():
    # Obter os parâmetros de data do formulário
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')

    # Verificar se as datas foram fornecidas
    if not data_inicio or not data_fim:
        flash('Por favor, selecione um intervalo de datas.')
        return render_template('relatorios.html', 
                               receitas_totais=0, 
                               despesas_totais=0, 
                               saldo_final=0, 
                               detalhes=[])

    # Converter as strings de data para objetos datetime
    data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d')
    data_fim = datetime.strptime(data_fim, '%Y-%m-%d')

    # Filtrar transações no intervalo de datas
    transacoes = Transacao.query.filter_by(usuario_id=current_user.id).filter(
        Transacao.data >= data_inicio,
        Transacao.data <= data_fim
    ).all()

    # Calcular os totais
    receitas_totais = sum(t.valor for t in transacoes if t.tipo == 'entrada')
    despesas_totais = sum(t.valor for t in transacoes if t.tipo == 'saida')
    saldo_final = receitas_totais - despesas_totais

    # Renderizar o template com os dados do relatório
    return render_template('relatorios.html',
                           receitas_totais=receitas_totais,
                           despesas_totais=despesas_totais,
                           saldo_final=saldo_final,
                           detalhes=transacoes)

@app.route('/relatorios/pdf')
@login_required
def relatorios_pdf():
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')

    if not data_inicio or not data_fim:
        flash('Por favor, selecione um intervalo de datas.')
        return redirect(url_for('relatorios'))

    data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d')
    data_fim = datetime.strptime(data_fim, '%Y-%m-%d')

    transacoes = Transacao.query.filter_by(usuario_id=current_user.id).filter(
        Transacao.data >= data_inicio,
        Transacao.data <= data_fim
    ).all()

    receitas_totais = sum(t.valor for t in transacoes if t.tipo == 'entrada')
    despesas_totais = sum(t.valor for t in transacoes if t.tipo == 'saida')
    saldo_final = receitas_totais - despesas_totais

    # Criar um dicionário para os dados do resumo
    resumo = {
        'data_inicio': data_inicio.strftime('%d/%m/%Y'),
        'data_fim': data_fim.strftime('%d/%m/%Y'),
        'receitas_totais': f"R$ {receitas_totais:.2f}",
        'despesas_totais': f"R$ {despesas_totais:.2f}",
        'saldo_final': f"R$ {saldo_final:.2f}"
    }

    html = render_template(
        'relatorios_pdf.html',  # utilize um template específico para o PDF
        resumo=resumo,
        detalhes=transacoes
    )

    result = io.BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=result)
    if pisa_status.err:
        return 'Erro na geração do PDF', 500

    response = make_response(result.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename="relatorio.pdf"'
    return response

# Inicializar banco de dados e criar categorias padrão
def inicializar_db():
    # db.create_all()
    
    # Criar categorias padrão se não existirem
    if Categoria.query.first() is None:
        categorias = [
            Categoria(nome='Salário', tipo='entrada'),
            Categoria(nome='Vendas', tipo='entrada'),
            Categoria(nome='Investimentos', tipo='entrada'),
            Categoria(nome='Outros', tipo='entrada'),
            Categoria(nome='Alimentação', tipo='saida'),
            Categoria(nome='Moradia', tipo='saida'),
            Categoria(nome='Transporte', tipo='saida'),
            Categoria(nome='Entretenimento', tipo='saida'),
            Categoria(nome='Saúde', tipo='saida'),
            Categoria(nome='Educação', tipo='saida'),
            Categoria(nome='Despesas Gerais', tipo='saida')
        ]
        
        for categoria in categorias:
            db.session.add(categoria)
        
        db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        inicializar_db()
    app.run(debug=True)