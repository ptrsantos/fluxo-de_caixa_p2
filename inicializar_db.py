
from app_antigo import Categoria, db, app

def inicializar_db():

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