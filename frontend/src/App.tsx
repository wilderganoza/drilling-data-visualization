import { Layout } from './components/layout'; // Componente de Layout
import { Card, CardHeader, CardTitle, CardContent, Button } from './components/ui'; // Componentes de UI (Card, CardContent, etc.)
import { useWells } from './hooks'; // Hook personalizado para obtener datos de pozos

// Componente principal de la aplicación
function App() {
  // Obtener datos de pozos usando hook personalizado (skip=0, limit=10)
  const { data: wellsData, isLoading, error } = useWells(0, 10);

  return (
    // Layout principal de la aplicación
    <Layout>
      {/* Contenedor principal con espaciado vertical */}
      <div className="space-y-6">
        {/* Encabezado del dashboard */}
        <div>
          <h1 className="text-3xl font-bold text-gray-100">Dashboard</h1>
          <p className="text-gray-400 mt-1">Overview of drilling analysis system</p>
        </div>

        {/* Grid de tarjetas de estadísticas */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Tarjeta: Total de pozos */}
          <Card>
            <CardContent className="py-6">
              <div className="text-center">
                <p className="text-4xl font-bold text-blue-500">
                  {isLoading ? '...' : wellsData?.total || 0}
                </p>
                <p className="text-sm text-gray-400 mt-2">Total Wells</p>
              </div>
            </CardContent>
          </Card>

          {/* Tarjeta: Base de datos de profundidad */}
          <Card>
            <CardContent className="py-6">
              <div className="text-center">
                <p className="text-4xl font-bold text-purple-500">
                  {isLoading ? '...' : wellsData?.total || 0}
                </p>
                <p className="text-sm text-gray-400 mt-2">Depth Records</p>
              </div>
            </CardContent>
          </Card>
        </div>

      </div>
    </Layout>
  );
}

// Exportar componente App como default
export default App;
